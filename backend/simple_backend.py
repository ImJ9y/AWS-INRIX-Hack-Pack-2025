#!/usr/bin/env python3
"""
Simple Fall Detection Backend - No WebSocket
For testing camera function with React frontend
"""
import cv2
import os
import time
import json
import uuid
import threading
from datetime import datetime
from decimal import Decimal
from ultralytics import YOLO
import numpy as np
from dotenv import load_dotenv
import boto3
from flask import Flask, jsonify, request
from flask_cors import CORS
import base64
from io import BytesIO

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

class SimpleFallDetector:
    def __init__(self):
        # Use pose model for better fall detection with keypoints
        self.model = YOLO("yolov8n-pose.pt")  # Pose model with 17 keypoints
        self.imgsz = int(os.getenv("YOLO_IMG_SIZE", "640"))
        self.use_tracking = True  # Enable persistent tracking
        self.aws_services = self.init_aws_services()
        self.fall_threshold_velocity = float(os.getenv('FALL_THRESHOLD_VELOCITY', '5.0'))  # Much higher threshold - 5.0
        self.fall_threshold_angle = float(os.getenv('FALL_THRESHOLD_ANGLE', '75'))  # Higher angle threshold - 75°
        self.emergency_severity_threshold = int(os.getenv('EMERGENCY_SEVERITY_THRESHOLD', '7'))  # Require higher severity
        self.verification_time = float(os.getenv('VERIFICATION_TIME_SECONDS', '5.0'))
        
        # Fall detection state - enhanced tracking
        self.person_positions = {}
        self.person_velocities = {}  # Track velocity history for acceleration detection
        self.person_angles = {}  # Track orientation change (pitch/roll)
        self.person_sizes = {}  # Track bounding box sizes for position
        self.person_head_positions = {}  # Track head positions (y-coordinate)
        self.person_center_positions = {}  # Track center of gravity
        self.person_aspect_ratios = {}  # Track body shape (elongation)
        self.person_accelerations = {}  # Track acceleration (velocity changes)
        self.person_motion_states = {}  # Track motion states: moving -> falling -> impact -> still
        self.person_fall_patterns = {}  # Track temporal pattern
        self.emergency_active = False
        self.emergency_start_time = None
        self.frame_count = 0
        self.camera_active = False
        self.cap = None
        
        # Statistics
        self.total_detections = 0
        self.total_emergencies = 0
        self.current_people_count = 0
        self.max_severity = 1
        self.last_frame = None
        self.fall_cooldown = {}
        self.latest_detection_data = []  # Store latest detection data for API
        
        # Temporal parameters
        self.fall_duration_threshold = 1.0  # <1s from upright to ground
        self.impact_detection_threshold = 0.2  # Velocity drops to near-zero in few frames
        self.stillness_threshold = 5  # Person stays still after impact
        
        # FPS tracking for temporal normalization
        self.fps = 30.0
        self.last_ts = time.time()
        self.fall_duration_frames = max(3, int(self.fps * 0.8))  # ~0.8s
        self.still_frames_needed = max(6, int(self.fps * 1.0))  # ~1s stillness
        
        # EMA smoothing stores
        self.ema_vnorm = {}
        self.ema_angle = {}
        self.ema_hip_y = {}
        
        # Severity history for hysteresis
        self.severity_history = {}  # Track per person
        self.high_severity_frames = {}  # Track consecutive high severity
    
    def init_aws_services(self):
        """Initialize AWS services"""
        try:
            return {
                's3': boto3.client('s3'),
                'dynamodb': boto3.resource('dynamodb'),
                'sns': boto3.client('sns'),
                'cloudwatch': boto3.client('cloudwatch')
            }
        except Exception as e:
            print(f"⚠️ AWS services not available: {e}")
            return None
    
    def ema(self, store_name, pid, value, alpha=0.3):
        """Exponential Moving Average smoothing helper"""
        store = getattr(self, store_name, {})
        last = store.get(pid, value)
        smoothed = alpha * value + (1 - alpha) * last
        store[pid] = smoothed
        setattr(self, store_name, store)
        return smoothed
    
    def calculate_velocity(self, person_id, new_position, box_size=None):
        """
        Enhanced velocity calculation with acceleration detection
        Detects rapid downward movement with noise filtering
        """
        if person_id not in self.person_positions:
            self.person_positions[person_id] = []
            self.person_velocities[person_id] = []
            self.person_accelerations[person_id] = []
        
        self.person_positions[person_id].append(new_position)
        if box_size:
            self.person_sizes[person_id] = box_size
        
        # Keep last 15 positions for better smoothing
        if len(self.person_positions[person_id]) > 15:
            self.person_positions[person_id] = self.person_positions[person_id][-15:]
        
        if len(self.person_positions[person_id]) < 5:
            return 0.0, 0.0  # Return velocity and acceleration
        
        positions = self.person_positions[person_id]
        
        # Calculate velocity from multiple frames with noise filtering
        recent_velocities = []
        for i in range(1, min(6, len(positions))):
            dx = positions[-i][0] - positions[-i-1][0]
            dy = positions[-i][1] - positions[-i-1][1]
            
            # Filter out small movements (likely noise)
            if abs(dx) < 2 and abs(dy) < 2:
                continue
            
            # Calculate velocity with downward emphasis
            if dy > 3:  # Only count significant downward movement
                velocity = np.sqrt(dx*dx + (dy * 2.5)**2)  # Reduced weight
            elif dy < -2:  # Moving up - penalize heavily
                velocity = np.sqrt(dx*dx + (dy * 0.1)**2) * 0.1
            else:  # Lateral or minor movement
                velocity = np.sqrt(dx*dx + (dy * 0.5)**2)
            
            recent_velocities.append(velocity)
        
        # Use median instead of mean to reduce impact of outliers
        if recent_velocities:
            avg_velocity = np.median(recent_velocities)
        else:
            avg_velocity = 0.0
        
        # Calculate acceleration (rate of change of velocity)
        acceleration = 0.0
        if len(self.person_velocities[person_id]) >= 3:
            # Use average of recent velocities for stability
            recent_avg = np.mean(self.person_velocities[person_id][-3:])
            if len(self.person_velocities[person_id]) >= 6:
                earlier_avg = np.mean(self.person_velocities[person_id][-6:-3])
                acceleration = recent_avg - earlier_avg
            else:
                acceleration = avg_velocity - self.person_velocities[person_id][-1]
        
        # Store velocity and acceleration history
        self.person_velocities[person_id].append(avg_velocity)
        self.person_accelerations[person_id].append(acceleration)
        if len(self.person_velocities[person_id]) > 15:
            self.person_velocities[person_id] = self.person_velocities[person_id][-15:]
            self.person_accelerations[person_id] = self.person_accelerations[person_id][-15:]
        
        return avg_velocity, acceleration
    
    def calculate_angle(self, person_id):
        """
        Enhanced angle calculation using HEAD POSITION (not bounding box center)
        Measures tilt from vertical to horizontal by tracking head movement
        """
        if person_id not in self.person_head_positions or len(self.person_head_positions[person_id]) < 5:
            return 0.0, 0.0  # Return angle and angular velocity
        
        head_positions = self.person_head_positions[person_id]
        
        # Calculate orientation angle based on HEAD movement (more accurate)
        angles = []
        
        for i in range(1, min(6, len(head_positions))):
            # Head Y position change (positive = moving down)
            dy = head_positions[-i] - head_positions[-i-1]
            
            # Filter very small movements
            if abs(dy) < 3:
                continue
            
            # Detect significant downward head movement (falling)
            if dy > 15:  # Head moving down rapidly
                # Calculate angle of descent (steepness of fall)
                # For now, we use dy magnitude as a proxy for angle
                # dy > 15 = steep angle, dy > 25 = very steep/near vertical
                if dy > 25:
                    angles.append(85)  # Very steep/near vertical fall
                elif dy > 18:
                    angles.append(75)  # Steep fall
                else:
                    angles.append(60)  # Moderate fall angle
        
        if not angles:
            return 0.0, 0.0
        
        # Use median to reduce impact of outliers
        current_angle = np.median(angles)
        
        # Calculate angular velocity (how fast the head/body is tilting)
        angular_velocity = 0.0
        if person_id in self.person_angles and len(self.person_angles[person_id]) >= 3:
            recent_avg = np.mean(self.person_angles[person_id][-3:])
            if len(self.person_angles[person_id]) >= 6:
                earlier_avg = np.mean(self.person_angles[person_id][-6:-3])
                angular_velocity = recent_avg - earlier_avg
            else:
                angular_velocity = current_angle - self.person_angles[person_id][-1]
        
        # Store angle history
        if person_id not in self.person_angles:
            self.person_angles[person_id] = []
        self.person_angles[person_id].append(current_angle)
        if len(self.person_angles[person_id]) > 15:
            self.person_angles[person_id] = self.person_angles[person_id][-15:]
        
        return current_angle, angular_velocity
    
    def detect_head_downward_motion(self, person_id, head_y, torso_y=None):
        """
        Detect head position relative to torso/hips
        Head below torso suggests uncontrolled descent
        Note: Head position is now stored before calling this function
        """
        if person_id not in self.person_head_positions:
            return 0.0
        
        if len(self.person_head_positions[person_id]) < 3:
            return 0.0
        
        head_positions = self.person_head_positions[person_id]
        
        # Calculate head downward velocity
        head_velocities = []
        for i in range(1, min(4, len(head_positions))):
            dy = head_positions[-i] - head_positions[-i-1]
            head_velocities.append(dy)
        
        avg_head_velocity = np.mean(head_velocities)
        
        # Detect rapid head drop (uncontrolled fall)
        if avg_head_velocity > 10:  # Head moving down rapidly
            total_drop = head_positions[-1] - head_positions[0]
            if total_drop > 25:  # Significant head drop
                return min(3.0, total_drop / 15)
        
        # Detect if head has fallen below starting position
        if len(head_positions) >= 5:
            initial_y = np.mean(head_positions[:3])
            recent_y = np.mean(head_positions[-3:])
            if recent_y > initial_y + 30:  # Head dropped significantly
                return min(2.0, (recent_y - initial_y) / 20)
        
        return 0.0
    
    def detect_body_shape_change(self, person_id, width, height):
        """
        Detect body posture shape change
        Body becomes elongated and horizontal (reduction in aspect ratio)
        """
        if person_id not in self.person_aspect_ratios:
            self.person_aspect_ratios[person_id] = []
        
        # Calculate aspect ratio (width/height)
        # Vertical person: aspect_ratio < 1
        # Horizontal person: aspect_ratio > 1
        aspect_ratio = width / height if height > 0 else 1.0
        
        self.person_aspect_ratios[person_id].append(aspect_ratio)
        if len(self.person_aspect_ratios[person_id]) > 10:
            self.person_aspect_ratios[person_id] = self.person_aspect_ratios[person_id][-10:]
        
        if len(self.person_aspect_ratios[person_id]) < 5:
            return 0.0
        
        # Check if body is becoming more horizontal
        recent_ratio = np.mean(self.person_aspect_ratios[person_id][-3:])
        earlier_ratio = np.mean(self.person_aspect_ratios[person_id][:3])
        
        # If body is becoming more horizontal (aspect ratio increasing)
        if recent_ratio > earlier_ratio * 1.3:
            return min(2.0, (recent_ratio - earlier_ratio) * 2)
        
        return 0.0
    
    def detect_impact(self, person_id, current_velocity, accel_history):
        """
        Detect impact: sudden stop in motion after rapid descent
        Velocity drops to near-zero in few frames after high velocity
        """
        if person_id not in self.person_motion_states:
            self.person_motion_states[person_id] = 'moving'
        
        # Check velocity history for impact pattern
        if len(self.person_velocities[person_id]) >= 5:
            recent_velocities = self.person_velocities[person_id][-5:]
            
            # Pattern: high velocity -> sudden drop
            max_velocity = max(recent_velocities[:-2])  # High velocity earlier
            recent_velocity = recent_velocities[-1]  # Current (low) velocity
            
            # If velocity dropped dramatically
            if max_velocity > self.fall_threshold_velocity * 2 and recent_velocity < max_velocity * 0.3:
                if self.person_motion_states[person_id] != 'impact':
                    self.person_motion_states[person_id] = 'impact'
                    return 3.0  # Strong indicator of impact
        
        # Detect stillness after impact
        if self.person_motion_states[person_id] == 'impact':
            # If velocity remains low
            if current_velocity < self.fall_threshold_velocity * 0.5:
                if person_id not in self.person_fall_patterns:
                    self.person_fall_patterns[person_id] = {'still_frames': 0}
                self.person_fall_patterns[person_id]['still_frames'] += 1
                
                # Person staying still after impact
                if self.person_fall_patterns[person_id]['still_frames'] > 3:
                    return 2.0  # Confirms fall (not getting up)
        
        return 0.0
    
    def analyze_temporal_pattern(self, person_id, v_norm, torso_angle):
        """
        FSM-based temporal pattern analysis
        Sequence: upright -> descending -> horizontal -> still
        Returns score when pattern is detected within temporal constraints
        """
        if person_id not in self.person_fall_patterns:
            self.person_fall_patterns[person_id] = {"stage": "none", "t0": 0, "k": 0, "m": 0}
        
        st = self.person_fall_patterns[person_id]
        
        # Stage 0: none -> descending (fast downward motion detected)
        if st["stage"] == "none" and v_norm > 0.8:  # Normalized velocity threshold
            st["stage"] = "descending"
            st["t0"] = self.frame_count
            st["k"] = 0
            st["m"] = 0
            return 0.0
        
        # Stage 1: descending -> horizontal (torso rotates past 70°)
        elif st["stage"] == "descending":
            if torso_angle > 70:  # Horizontal-ish
                st["k"] += 1
                if (self.frame_count - st["t0"] <= self.fall_duration_frames) and (st["k"] >= 2):
                    st["stage"] = "horizontal"
                    return 1.5  # Medium pattern
            else:
                # Timeout if too long without rotation
                if self.frame_count - st["t0"] > self.fall_duration_frames:
                    st["stage"] = "none"
                    st["k"] = 0
        
        # Stage 2: horizontal -> still (wait for stillness)
        elif st["stage"] == "horizontal":
            st["m"] += 1
            if st["m"] >= self.still_frames_needed:
                return 2.5  # Strong pattern - complete fall sequence detected
        
        # Reset if still for too long
        if v_norm < 0.2 and st["stage"] != "none" and (self.frame_count - st["t0"]) > self.still_frames_needed * 2:
            st["stage"] = "none"
            st["k"] = 0
            st["m"] = 0
        
        return 0.0
    
    def assess_severity(self, velocity, acceleration, angle, angular_velocity, person_id=None, 
                       head_score=0.0, shape_score=0.0, impact_score=0.0, pattern_score=0.0):
        """
        Comprehensive severity assessment using all indicators
        Only raises severity if MULTIPLE strong indicators are present
        """
        # Start with base severity
        severity = 1
        
        # Count strong indicators (only count if they exceed reasonable thresholds)
        strong_indicators = 0
        
        # 1. High downward velocity/acceleration - need BOTH high velocity AND acceleration
        velocity_points = 0
        if velocity > self.fall_threshold_velocity * 1.5:  # Higher threshold
            velocity_points = min(3.0, ((velocity - self.fall_threshold_velocity * 1.5) / self.fall_threshold_velocity) * 3)
            
            # Only count as strong if velocity is VERY high
            if velocity > self.fall_threshold_velocity * 2:
                strong_indicators += 1
        
        # Acceleration bonus - only if velocity is already high
        if velocity > self.fall_threshold_velocity and acceleration > 1.0:  # Higher threshold
            velocity_points *= 1.3
        
        # 2. Body orientation change - need significant ANGLE CHANGE (not absolute angle)
        angle_points = 0
        # ONLY score if there's RECENT change in angle (angular velocity is high)
        # This prevents detecting a person who's just sitting/lying still
        if angular_velocity > 5 and angle > self.fall_threshold_angle:
            angle_points = min(3.0, ((angle - self.fall_threshold_angle) / 30) * 3)
            
            # Only count as strong if angle is VERY steep AND rapidly changing
            if angle > self.fall_threshold_angle + 15 and angular_velocity > 15:
                strong_indicators += 1
        
        # Require BOTH high angle AND high angular velocity (rapid orientation change)
        if angle > self.fall_threshold_angle and angular_velocity > 10:
            angle_points *= 1.1
        elif angular_velocity < 5:
            # Reduce score if person is not moving (static position)
            angle_points *= 0.3
        
        # 3-6. Other indicators - only count if they're significant
        head_points = min(2, int(head_score)) if head_score > 1.5 else 0
        shape_points = min(2, int(shape_score)) if shape_score > 1.0 else 0
        impact_points = min(2, int(impact_score)) if impact_score > 2.0 else 0  # Only strong impacts
        pattern_points = min(1, int(pattern_score)) if pattern_score > 1.0 else 0
        
        # Only count as strong indicators if significant
        if head_score > 1.5: strong_indicators += 1
        if shape_score > 1.0: strong_indicators += 1
        if impact_score > 2.0: strong_indicators += 1
        if pattern_score > 1.0: strong_indicators += 1
        
        # Add up points
        severity += int(velocity_points) + int(angle_points) + int(head_points) + int(shape_points) + int(impact_points) + int(pattern_points)
        
        # 7. Bonus: Only if MULTIPLE strong indicators (3 or more)
        if strong_indicators >= 3:
            severity += 1  # Multiple confirmations = higher confidence
        
        # CRITICAL: If velocity is very low (person is static), force severity to 1
        # This prevents false positives when someone is just sitting/lying still
        if velocity < 1.0:  # Very low velocity (person is not moving)
            # Only allow severity > 1 if there are at least 3 strong indicators
            # This ensures we're only detecting actual falls, not static positions
            if strong_indicators < 3:
                severity = 1  # Force to normal if person is not moving and not enough indicators
        
        # Cap severity at 10, but keep normal movement at 1
        return min(10, max(1, severity))
    
    def store_emergency_video(self, frame):
        """Store emergency video frame in S3"""
        if not self.aws_services:
            print("📹 [DEMO] Would store video in S3")
            return "demo-video-url"
        
        try:
            bucket_name = os.getenv('AWS_S3_EMERGENCY_BUCKET', 'fall-detection-emergency-data-dev-800680963266')
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"emergency_{timestamp}_{uuid.uuid4().hex[:8]}.jpg"
            
            # Encode frame as JPEG
            _, buffer = cv2.imencode('.jpg', frame)
            
            # Upload to S3
            self.aws_services['s3'].put_object(
                Bucket=bucket_name,
                Key=f"emergency-images/{filename}",
                Body=buffer.tobytes(),
                ContentType='image/jpeg'
            )
            
            print(f"📹 Emergency image stored: s3://{bucket_name}/emergency-images/{filename}")
            return f"s3://{bucket_name}/emergency-images/{filename}"
            
        except Exception as e:
            print(f"❌ Failed to store emergency video: {e}")
            return None
    
    def save_emergency_event(self, severity, velocity, angle, video_url):
        """Save emergency event to DynamoDB"""
        if not self.aws_services:
            print(f"📊 [DEMO] Would save event: Severity {severity}/10")
            return
        
        try:
            table_name = os.getenv('AWS_DYNAMODB_EVENTS_TABLE', 'fall-detection-events-dev')
            table = self.aws_services['dynamodb'].Table(table_name)
            
            event_id = str(uuid.uuid4())
            timestamp = datetime.now().isoformat()
            
            item = {
                'event_id': event_id,
                'timestamp': timestamp,
                'severity': int(severity),
                'velocity': Decimal(str(velocity)),
                'angle': Decimal(str(angle)),
                'video_url': video_url,
                'status': 'active',
                'ttl': int(time.time()) + 86400  # 24 hours
            }
            
            table.put_item(Item=item)
            print(f"📊 Emergency event saved: {event_id}")
            
        except Exception as e:
            print(f"❌ Failed to save emergency event: {e}")
    
    def process_frame(self, frame):
        """Process a single frame for fall detection with pose keypoints"""
        self.frame_count += 1
        
        # Update FPS
        now = time.time()
        dt = max(1e-3, now - self.last_ts)
        self.fps = 0.9 * self.fps + 0.1 * (1.0 / dt)
        self.last_ts = now
        self.fall_duration_frames = max(3, int(self.fps * 0.8))
        self.still_frames_needed = max(6, int(self.fps * 1.0))
        
        # Run YOLO detection with tracking
        if self.use_tracking:
            results = self.model.track(
                source=frame,
                persist=True,
                imgsz=self.imgsz,
                verbose=False,
                tracker="bytetrack.yaml"
            )
        else:
            results = self.model(frame, imgsz=self.imgsz, verbose=False)
        
        person_count = 0
        max_severity = self.max_severity  # Keep previous max severity
        detections = []
        H, W = frame.shape[:2]  # Frame height and width for ground detection
        
        for r in results:
            kps = getattr(r, "keypoints", None)  # Pose keypoints
            boxes = r.boxes
            if boxes is not None:
                for i, box in enumerate(boxes):
                    if int(box.cls) == 0:  # person class
                        # Check if it's a full body detection (not just face)
                        # In YOLO, person class detects whole body, but we can filter by size
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                        width = x2 - x1
                        height = y2 - y1
                        
                        # Only process if it's a reasonable sized detection (full body)
                        # Filters out tiny face detections
                        if width > 50 and height > 100:  # Minimum body size
                            person_count += 1
                            
                            # Get tracking ID or use person count
                            pid = int(box.id) if getattr(box, 'id', None) is not None else person_count
                            
                            # Get person position (center of bounding box)
                            center_x = int((x1 + x2) / 2)
                            center_y = int((y1 + y2) / 2)
                            box_size = (width, height)
                            
                            # Process pose keypoints if available
                            angle_to_vertical = 0.0
                            v_norm = 0.0
                            near_floor = False
                            
                            if kps is not None and kps.xy is not None and len(kps.xy[i]) > 0:
                                kp = kps.xy[i].cpu().numpy()  # shape (17, 2) for COCO
                                # Indexes: 5=left_shoulder, 6=right_shoulder, 11=left_hip, 12=right_hip
                                if len(kp) > 12:
                                    ls, rs, lh, rh = kp[5], kp[6], kp[11], kp[12]
                                    # Check if keypoints are valid (not zeros)
                                    if all(np.sum(k > 0) > 0 for k in [ls, rs, lh, rh]):
                                        shoulder_mid = ((ls[0]+rs[0])/2.0, (ls[1]+rs[1])/2.0)
                                        hip_mid = ((lh[0]+rh[0])/2.0, (lh[1]+rh[1])/2.0)
                                        
                                        # Torso vector and angle to vertical
                                        vx, vy = (hip_mid[0]-shoulder_mid[0], hip_mid[1]-shoulder_mid[1])
                                        torso_len = max(1.0, np.hypot(vx, vy))
                                        angle_to_vertical = np.degrees(np.arctan2(abs(vx), abs(vy)))  # 0=vertical, 90=horizontal
                                        
                                        # Track hip midpoint for normalized vertical velocity
                                        if pid not in self.person_center_positions:
                                            self.person_center_positions[pid] = []
                                        self.person_center_positions[pid].append(hip_mid)
                                        
                                        # Calculate normalized vertical velocity: Δy / torso_len
                                        hist = self.person_center_positions[pid]
                                        if len(hist) >= 2:
                                            dy = hist[-1][1] - hist[-2][1]
                                            v_norm = float(dy / torso_len)
                                        
                                        # Keep short window for smoothing
                                        if len(hist) > 20:
                                            self.person_center_positions[pid] = hist[-20:]
                                        
                                        # Ground/lying detection
                                        near_floor = (max(y1, y2) > 0.85 * H) or (hip_mid[1] > 0.80 * H)
                            
                            # Get head position (top of bounding box - y1 coordinate)
                            head_y = int(y1)
                            
                            # Store head position FIRST (for angle calculation)
                            if pid not in self.person_head_positions:
                                self.person_head_positions[pid] = []
                            self.person_head_positions[pid].append(head_y)
                            if len(self.person_head_positions[pid]) > 15:
                                self.person_head_positions[pid] = self.person_head_positions[pid][-15:]
                            
                            # Apply EMA smoothing to pose-based signals
                            v_norm_smooth = self.ema("ema_vnorm", pid, v_norm, alpha=0.25)
                            angle_smooth = self.ema("ema_angle", pid, angle_to_vertical, alpha=0.2)
                            
                            # Calculate velocity and angle (fallback to bbox method if pose data not available)
                            velocity, acceleration = self.calculate_velocity(pid, (center_x, center_y), box_size)
                            angle, angular_velocity = self.calculate_angle(pid)
                            
                            # Use pose-based signals if available, otherwise use bbox-based
                            if angle_to_vertical > 0:
                                angle = angle_to_vertical
                            if v_norm > 0:
                                velocity = max(velocity, v_norm_smooth * 10.0)  # Scale to similar range
                            
                            # Detect head downward motion (redundant now since angle uses head, but keeping for compatibility)
                            head_downward_score = self.detect_head_downward_motion(pid, head_y)
                            
                            # Detect body shape change
                            shape_score = self.detect_body_shape_change(pid, width, height)
                            
                            # Detect impact (with pose enhancement for near_floor)
                            impact_score = self.detect_impact(pid, velocity, acceleration)
                            if near_floor and angle_smooth > 70:
                                impact_score += 1.0  # Boost impact if near ground and horizontal
                            
                            # Analyze temporal pattern (use pose-based signals)
                            pattern_score = self.analyze_temporal_pattern(pid, v_norm_smooth, angle_smooth)
                            
                            # Assess severity with person_id and all scores
                            severity = self.assess_severity(velocity, acceleration, angle, angular_velocity, pid, 
                                                           head_downward_score, shape_score, impact_score, pattern_score)
                            max_severity = max(max_severity, severity)
                            
                            # Store detection data with all indicators
                            detections.append({
                                'id': pid,
                                'bbox': [int(x1), int(y1), int(x2), int(y2)],
                                'center': [center_x, center_y],
                                'velocity': float(velocity),
                                'acceleration': float(acceleration),
                                'angle': float(angle),
                                'angular_velocity': float(angular_velocity),
                                'head_score': float(head_downward_score),
                                'shape_score': float(shape_score),
                                'impact_score': float(impact_score),
                                'pattern_score': float(pattern_score),
                                'severity': severity
                            })
                            
                            # Draw bounding box and info
                            color = (0, 255, 0) if severity < self.emergency_severity_threshold else (0, 0, 255)
                            cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
                            
                            # Add comprehensive text info
                            head_status = "H↓" if head_downward_score > 0 else "H-"
                            shape_status = "S🔄" if shape_score > 0 else "S-"
                            impact_status = "I!" if impact_score > 0 else "I-"
                            pattern_status = "P✓" if pattern_score > 0 else "P-"
                            
                            info_text = f"P{pid}: S{severity}/10 V{velocity:.1f} A{angle:.0f}° Vn{v_norm_smooth:.2f} {head_status}{shape_status}{impact_status}{pattern_status}"
                            cv2.putText(frame, info_text, (int(x1), int(y1)-10), 
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
        
        # Update statistics
        self.current_people_count = person_count
        self.total_detections += 1
        
        # Update max_severity - always track the peak severity seen
        # But allow it to decay when falls clear
        if max_severity > self.max_severity:
            # New higher severity detected - update max
            self.max_severity = max_severity
        elif max_severity < self.max_severity and max_severity <= 1:
            # No fall currently detected and we had a previous high severity
            # Decay the max_severity faster - reduce by 1.0 per frame
            self.max_severity = max(1, self.max_severity - 1.0)
        
        # Check for emergency based on CURRENT severity (not max)
        emergency_data = None
        
        # Track person status
        current_person_status = 'normal'
        if detections:
            # Check if any person shows fall indicators
            for det in detections:
                if det.get('severity', 1) >= self.emergency_severity_threshold:
                    current_person_status = 'fall_detected'
                    break
                elif det.get('severity', 1) > 3:
                    current_person_status = 'suspicious'
        
        if current_person_status == 'fall_detected':
            # New fall detected - start emergency tracking
            if not self.emergency_active:
                self.emergency_active = True
                self.emergency_start_time = time.time()
                
                # Store emergency frame for AI analysis
                video_url = self.store_emergency_video(frame)
                if detections:
                    avg_velocity = sum([d['velocity'] for d in detections]) / len(detections)
                    avg_angle = sum([d['angle'] for d in detections]) / len(detections)
                    
                    # Save event for AI analysis
                    self.save_emergency_event(max_severity, avg_velocity, avg_angle, video_url)
                
                emergency_data = {
                    'type': 'emergency_alert',
                    'severity': max_severity,
                    'message': f'🚨 FALL DETECTED - AI Analysis Starting...',
                    'verification_time': self.verification_time,
                    'video_url': video_url
                }
                
                print(f"🚨 Emergency triggered! Severity: {max_severity}/10")
                print(f"📊 Saving data for AI analysis: velocity={avg_velocity:.2f}, angle={avg_angle:.1f}°")
            else:
                # Continue monitoring during active emergency
                elapsed_time = time.time() - self.emergency_start_time
                
                if elapsed_time >= self.verification_time:
                    # Verification complete - this triggers AI analysis and 911 call
                    emergency_data = {
                        'type': 'emergency_verified',
                        'severity': max_severity,
                        'message': f'✅ Verified: Person still showing fall indicators. Ready for AI analysis and emergency response.',
                        'elapsed_time': elapsed_time,
                        'ai_analysis_ready': True
                    }
                    
                    print(f"✅ Emergency verified after {elapsed_time:.1f}s")
                    print("🤖 Would trigger: AI analysis → 911 call")
                else:
                    # Still in verification period
                    remaining_time = self.verification_time - elapsed_time
                    emergency_data = {
                        'type': 'emergency_verifying',
                        'severity': max_severity,
                        'message': f'Verifying emergency... {remaining_time:.1f}s remaining',
                        'remaining_time': remaining_time
                    }
        elif current_person_status == 'normal':
            # Person recovered - clear emergency
            if self.emergency_active:
                elapsed_time = time.time() - self.emergency_start_time
                
                # Only clear if they've been normal for at least 3 seconds
                if elapsed_time > 3.0:
                    self.emergency_active = False
                    self.emergency_start_time = None
                    emergency_data = {
                        'type': 'emergency_cleared',
                        'message': '✅ Person recovered - Emergency cleared',
                        'recovery_time': elapsed_time
                    }
                    print(f"✅ Emergency cleared after {elapsed_time:.1f}s - Person recovered")
                else:
                    # Still monitoring for verification
                    emergency_data = {
                        'type': 'monitoring_recovery',
                        'severity': max_severity,
                        'message': f'Monitoring person recovery... ({elapsed_time:.1f}s)',
                        'elapsed_time': elapsed_time
                    }
        
        # Add frame info
        cv2.putText(frame, f"Frame: {self.frame_count}", (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.putText(frame, f"People: {person_count}", (10, 70), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.putText(frame, f"Current Severity: {max_severity}/10", (10, 110), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.putText(frame, f"Peak Severity: {self.max_severity}/10", (10, 150), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2)
        
        if self.emergency_active:
            elapsed = time.time() - self.emergency_start_time
            cv2.putText(frame, f"EMERGENCY: {elapsed:.1f}s", (10, 190), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
            cv2.putText(frame, "AI Analysis Ready", (10, 230), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 255), 2)
        
        # Store last frame
        self.last_frame = frame
        
        # Store latest detection data for API
        self.latest_detection_data = detections
        
        return frame, detections, emergency_data
    
    def start_camera(self):
        """Start camera detection"""
        if self.camera_active:
            return False
        
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            return False
        
        self.camera_active = True
        
        def camera_loop():
            while self.camera_active:
                ret, frame = self.cap.read()
                if not ret:
                    break
                
                # Process frame
                processed_frame, detections, emergency_data = self.process_frame(frame)
                
                time.sleep(0.033)  # ~30 FPS
        
        # Start camera thread
        self.camera_thread = threading.Thread(target=camera_loop)
        self.camera_thread.daemon = True
        self.camera_thread.start()
        
        return True
    
    def stop_camera(self):
        """Stop camera detection"""
        self.camera_active = False
        if self.cap:
            self.cap.release()
        return True
    
    def get_latest_frame(self):
        """Get the latest processed frame as base64"""
        if self.last_frame is None:
            return None
        
        # Convert frame to base64
        _, buffer = cv2.imencode('.jpg', self.last_frame)
        frame_base64 = base64.b64encode(buffer).decode('utf-8')
        return frame_base64

# Initialize fall detection backend
fall_detector = SimpleFallDetector()

# Flask routes
@app.route('/')
def index():
    return jsonify({
        'message': 'Fall Detection Backend API',
        'status': 'running',
        'endpoints': {
            '/api/status': 'GET - Get system status',
            '/api/start_camera': 'POST - Start camera detection',
            '/api/stop_camera': 'POST - Stop camera detection',
            '/api/latest_frame': 'GET - Get latest camera frame',
            '/api/detections': 'GET - Get latest detection data'
        }
    })

@app.route('/api/status')
def get_status():
    return jsonify({
        'camera_active': fall_detector.camera_active,
        'aws_services': fall_detector.aws_services is not None,
        'stats': {
            'total_detections': fall_detector.total_detections,
            'total_emergencies': fall_detector.total_emergencies,
            'current_people_count': fall_detector.current_people_count,
            'max_severity': fall_detector.max_severity,
            'frame_count': fall_detector.frame_count
        }
    })

@app.route('/api/start_camera', methods=['POST'])
def start_camera():
    success = fall_detector.start_camera()
    return jsonify({'success': success})

@app.route('/api/stop_camera', methods=['POST'])
def stop_camera():
    success = fall_detector.stop_camera()
    return jsonify({'success': success})

@app.route('/api/latest_frame')
def get_latest_frame():
    frame_base64 = fall_detector.get_latest_frame()
    if frame_base64:
        return jsonify({
            'frame': frame_base64,
            'timestamp': datetime.now().isoformat()
        })
    else:
        return jsonify({'error': 'No frame available'}), 404

@app.route('/api/detections')
def get_detections():
    # Return the latest detection data with all fields
    detections_dict = {}
    for det in fall_detector.latest_detection_data:
        detections_dict[det['id']] = {
            'velocity': det.get('velocity', 0.0),
            'acceleration': det.get('acceleration', 0.0),
            'angle': det.get('angle', 0.0),
            'angular_velocity': det.get('angular_velocity', 0.0),
            'center': det.get('center', [0, 0]),
            'severity': det.get('severity', 1)
        }
    
    return jsonify({
        'detections': detections_dict,
        'stats': {
            'total_detections': fall_detector.total_detections,
            'total_emergencies': fall_detector.total_emergencies,
            'current_people_count': fall_detector.current_people_count,
            'max_severity': fall_detector.max_severity,
            'emergency_active': fall_detector.emergency_active
        }
    })

if __name__ == '__main__':
    print("🚀 Starting Simple Fall Detection Backend")
    print("=" * 50)
    print("✅ Features:")
    print("   • Real-time camera detection")
    print("   • REST API endpoints")
    print("   • AWS services integration")
    print("")
    print("🌐 Server will be available at:")
    print("   • HTTP: http://localhost:5001")
    print("")
    print("📋 Available endpoints:")
    print("   • GET  /api/status")
    print("   • POST /api/start_camera")
    print("   • POST /api/stop_camera")
    print("   • GET  /api/latest_frame")
    print("   • GET  /api/detections")
    print("")
    
    app.run(debug=True, host='0.0.0.0', port=5001)
