#!/usr/bin/env python3
"""
Simple Fall Detection Backend - No WebSocket
For testing camera function with React frontend
"""
import base64
import json
import os
import sys
import threading
import time
import uuid
from datetime import datetime
from decimal import Decimal
from io import BytesIO

import boto3
import cv2
import numpy as np
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from ultralytics import YOLO

sys.path.append(os.path.join(os.path.dirname(__file__), "analyze_fall"))

# Load environment variables
load_dotenv()

# Import Gemini analyzer
try:
    import sys

    sys.path.insert(0, os.path.dirname(__file__))
    from analyze_fall.analyze import EmergencyImageAnalyzer

    gemini_analyzer = EmergencyImageAnalyzer()
    print("Gemini AI Analyzer loaded")
except Exception as e:
    print(f"Gemini analyzer not available: {e}")
    gemini_analyzer = None

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes


class SimpleFallDetector:
    def __init__(self):
        # Use pose model for better fall detection
        self.model = YOLO("yolov8n-pose.pt")
        self.imgsz = int(os.getenv("YOLO_IMG_SIZE", "640"))
        self.use_tracking = True
        self.tracker_cfg = os.getenv("TRACKER_CFG", "bytetrack.yaml")

        self.aws_services = self.init_aws_services()
        self.fall_threshold_velocity = float(
            os.getenv("FALL_THRESHOLD_VELOCITY", "0.8")
        )  # Normalized velocity threshold
        self.fall_threshold_angle = float(
            os.getenv("FALL_THRESHOLD_ANGLE", "70")
        )  # Torso angle threshold
        self.emergency_severity_threshold = int(
            os.getenv("EMERGENCY_SEVERITY_THRESHOLD", "7")
        )  # Higher threshold for pose-based
        self.verification_time = float(os.getenv("VERIFICATION_TIME_SECONDS", "5.0"))

        # Pose-based fall detection state
        self.person_positions = {}  # Legacy - keep for compatibility
        self.person_center_positions = {}  # Hip midpoints for normalized velocity
        self.person_head_positions = {}  # Legacy head positions
        self.person_velocities = {}  # Track velocity history
        self.person_angles = {}  # Track torso angle history
        self.person_sizes = {}  # Track bounding box sizes
        self.person_fall_patterns = {}  # State machine for each person

        # FPS tracking and normalization
        self.last_ts = time.time()
        self.fps = 30.0
        self.fall_duration_frames = max(3, int(self.fps * 0.8))  # Fast descent < ~0.8s
        self.still_frames_needed = max(6, int(self.fps * 1.0))  # ~1s stillness

        # Signal smoothing
        self.ema_vnorm = {}  # EMA for normalized velocity
        self.ema_angle = {}  # EMA for torso angle

        # Emergency state
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
        self.fall_cooldown = {}  # Prevent duplicate fall detection
        self.last_ai_analysis = None  # Store latest Gemini analysis
        self.last_emergency_data = None  # Store latest emergency detection

    def init_aws_services(self):
        """Initialize AWS services"""
        try:
            return {
                "s3": boto3.client("s3"),
                "dynamodb": boto3.resource("dynamodb"),
                "sns": boto3.client("sns"),
                "cloudwatch": boto3.client("cloudwatch"),
            }
        except Exception as e:
            print(f" AWS services not available: {e}")
            return None

    def ema(self, key, pid, value, alpha=0.3):
        """Simple EMA smoothing helper"""
        store = getattr(self, key, {})
        last = store.get(pid, value)
        smoothed = alpha * value + (1 - alpha) * last
        store[pid] = smoothed
        setattr(self, key, store)
        return smoothed

    def analyze_temporal_pattern(self, pid, v_norm, torso_angle):
        """State machine for fall detection pattern"""
        st = self.person_fall_patterns.setdefault(
            pid, {"stage": "none", "t0": 0, "k": 0, "m": 0}
        )

        if st["stage"] == "none" and v_norm > 0.8:  # Fast descent detected
            st["stage"] = "descending"
            st["t0"] = self.frame_count
        elif st["stage"] == "descending":
            if torso_angle > 70:  # Horizontal-ish
                st["k"] += 1
                if (
                    self.frame_count - st["t0"] <= self.fall_duration_frames
                    and st["k"] >= 2
                ):
                    st["stage"] = "horizontal"
            else:
                # Timeout - reset if too long
                if self.frame_count - st["t0"] > self.fall_duration_frames:
                    st["stage"] = "none"
                    st["k"] = 0
        elif st["stage"] == "horizontal":
            # Wait for stillness measured via velocity < threshold
            st["m"] += 1
            if st["m"] >= self.still_frames_needed:
                return 2.5  # Strong pattern detected
        return 0.0

    def assess_severity_pose(
        self, velocity, angle, pid, v_norm, torso_angle, pattern_score, near_floor
    ):
        """Enhanced severity assessment using pose-based features"""
        severity = 1.0  # Base severity

        # Velocity component (normalized)
        if v_norm > 0.8:  # Fast descent
            severity += 2.0
        elif v_norm > 0.5:  # Moderate descent
            severity += 1.0

        # Torso angle component
        if torso_angle > 80:  # Very horizontal
            severity += 2.5
        elif torso_angle > 70:  # Horizontal
            severity += 1.5
        elif torso_angle > 60:  # Leaning
            severity += 0.5

        # Pattern component (state machine)
        severity += pattern_score

        # Ground/floor component
        if near_floor and torso_angle > 70:
            severity += 1.0

        # False positive suppression rules
        # Sit/stand transitions: large knee bend but torso stays < 45 degrees
        if torso_angle < 45 and v_norm > 0.6:
            severity -= 1.0  # Likely sitting/standing

        # Tying shoes/leaning: torso > 60 degrees but hip doesn't drop much
        if torso_angle > 60 and v_norm < 0.3:
            severity -= 0.5  # Likely bending/leaning

        # Ensure severity is within bounds
        severity = max(1.0, min(10.0, severity))

        return severity

    def calculate_velocity(self, person_id, new_position, box_size=None):
        """Calculate velocity with improved filtering and smoothing"""
        if person_id not in self.person_positions:
            self.person_positions[person_id] = []
            self.person_velocities[person_id] = []

        self.person_positions[person_id].append(new_position)
        if box_size:
            self.person_sizes[person_id] = box_size

        # Keep only last 10 positions for better averaging
        if len(self.person_positions[person_id]) > 10:
            self.person_positions[person_id] = self.person_positions[person_id][-10:]

        if len(self.person_positions[person_id]) < 3:
            return 0.0

        positions = self.person_positions[person_id]

        # Calculate velocity from multiple recent frames (more stable)
        velocities = []
        for i in range(1, min(4, len(positions))):  # Use last 3 frames
            dx = positions[-i][0] - positions[-i - 1][0]
            dy = positions[-i][1] - positions[-i - 1][1]

            # Normalize by frame time (assuming ~30 FPS)
            dt = 1.0  # 1 frame
            vx = dx / dt
            vy = dy / dt

            # Weight downward movement heavily (falling)
            if vy > 0:  # Moving down
                velocity = np.sqrt(vx * vx + vy * vy * 3.0)  # Weight downward 3x
            else:  # Moving up (unlikely to be fall)
                velocity = np.sqrt(vx * vx + vy * vy) * 0.3

            velocities.append(velocity)

        # Average the velocities for stability
        avg_velocity = np.mean(velocities)

        # Store velocity history for trend analysis
        self.person_velocities[person_id].append(avg_velocity)
        if len(self.person_velocities[person_id]) > 5:
            self.person_velocities[person_id] = self.person_velocities[person_id][-5:]

        return avg_velocity

    def calculate_angle(self, person_id):
        """Calculate body angle with improved multi-frame analysis"""
        if (
            person_id not in self.person_positions
            or len(self.person_positions[person_id]) < 4
        ):
            return 0.0

        positions = self.person_positions[person_id]

        # Calculate angles from multiple frame pairs for stability
        angles = []

        # Analyze last 4 frames
        for i in range(1, min(4, len(positions))):
            dx = positions[-i][0] - positions[-i - 1][0]
            dy = positions[-i][1] - positions[-i - 1][1]

            # Detect downward movement (fall)
            if dy > 3:  # Significant downward movement
                if abs(dx) > 1:
                    angle = np.degrees(np.arctan(abs(dy) / abs(dx)))
                    if angle > 30:  # Steep angle
                        angles.append(min(angle, 85))  # Cap at 85 degrees
                else:
                    angles.append(85)  # Nearly vertical fall

            # Detect sideways falls with some downward component
            elif abs(dx) > 8 and dy > 2:  # Lateral movement with slight downward
                angle = np.degrees(np.arctan(abs(dx) / abs(dy)))
                # Convert to tilt angle (how far from vertical)
                angles.append(min(angle, 60))

        if not angles:
            return 0.0

        # Store angle history
        avg_angle = np.mean(angles)
        if person_id not in self.person_angles:
            self.person_angles[person_id] = []
        self.person_angles[person_id].append(avg_angle)
        if len(self.person_angles[person_id]) > 5:
            self.person_angles[person_id] = self.person_angles[person_id][-5:]

        return avg_angle

    def assess_severity(self, velocity, angle, person_id=None):
        """Assess fall severity with velocity trend analysis"""
        severity = 1

        # Velocity component (0-4 points) with trend analysis
        if velocity > self.fall_threshold_velocity:
            # Check velocity trend (increasing velocity = more severe fall)
            velocity_trend = 1.0
            if person_id and person_id in self.person_velocities:
                vel_history = self.person_velocities[person_id]
                if len(vel_history) >= 3:
                    # Check if velocity is increasing (acceleration)
                    recent_avg = np.mean(vel_history[-2:])
                    earlier_avg = np.mean(vel_history[:-2])
                    if recent_avg > earlier_avg * 1.2:  # 20% increase
                        velocity_trend = 1.5  # Boost severity if accelerating

            max_velocity = self.fall_threshold_velocity * 2.5
            if velocity >= max_velocity:
                velocity_score = 4 * velocity_trend
            else:
                velocity_score = (
                    (
                        (velocity - self.fall_threshold_velocity)
                        / (max_velocity - self.fall_threshold_velocity)
                    )
                    * 4
                    * velocity_trend
                )

            severity += min(4, int(velocity_score))

        # Angle component (0-4 points) with trend analysis
        if angle > self.fall_threshold_angle:
            # Check angle trend (increasing angle = more severe fall)
            angle_trend = 1.0
            if person_id and person_id in self.person_angles:
                angle_history = self.person_angles[person_id]
                if len(angle_history) >= 2:
                    # Check if angle is increasing
                    if angle_history[-1] > angle_history[-2] * 1.1:  # 10% increase
                        angle_trend = 1.3  # Boost severity if angle increasing

            max_angle = self.fall_threshold_angle + 50
            if angle >= max_angle:
                angle_score = 4 * angle_trend
            else:
                angle_score = (
                    (
                        (angle - self.fall_threshold_angle)
                        / (max_angle - self.fall_threshold_angle)
                    )
                    * 4
                    * angle_trend
                )

            severity += min(4, int(angle_score))

        # Bonus point if both indicators are present (definite fall)
        if (
            velocity > self.fall_threshold_velocity
            and angle > self.fall_threshold_angle
        ):
            severity += 1

        # Bonus point if very high velocity (rapid fall)
        if velocity > self.fall_threshold_velocity * 3:
            severity += 1

        return min(10, max(1, severity))

    def store_emergency_video(self, frame):
        """Store emergency video frame in S3"""
        if not self.aws_services:
            print(" [DEMO] Would store video in S3")
            return "demo-video-url"

        try:
            bucket_name = os.getenv(
                "AWS_S3_EMERGENCY_BUCKET",
                "fall-detection-emergency-data-dev-800680963266",
            )
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"emergency_{timestamp}_{uuid.uuid4().hex[:8]}.jpg"

            # Encode frame as JPEG
            _, buffer = cv2.imencode(".jpg", frame)

            # Upload to S3
            self.aws_services["s3"].put_object(
                Bucket=bucket_name,
                Key=f"emergency-images/{filename}",
                Body=buffer.tobytes(),
                ContentType="image/jpeg",
            )

            print(
                f" Emergency image stored: s3://{bucket_name}/emergency-images/{filename}"
            )
            return f"s3://{bucket_name}/emergency-images/{filename}"

        except Exception as e:
            print(f" Failed to store emergency video: {e}")
            return None

    def save_emergency_event(self, severity, velocity, angle, video_url):
        """Save emergency event to DynamoDB"""
        if not self.aws_services:
            print(f" [DEMO] Would save event: Severity {severity}/10")
            return

        try:
            table_name = os.getenv(
                "AWS_DYNAMODB_EVENTS_TABLE", "fall-detection-events-dev"
            )
            table = self.aws_services["dynamodb"].Table(table_name)

            event_id = str(uuid.uuid4())
            timestamp = datetime.now().isoformat()

            item = {
                "event_id": event_id,
                "timestamp": timestamp,
                "severity": int(severity),
                "velocity": Decimal(str(velocity)),
                "angle": Decimal(str(angle)),
                "video_url": video_url,
                "status": "active",
                "ttl": int(time.time()) + 86400,  # 24 hours
            }

            table.put_item(Item=item)
            print(f" Emergency event saved: {event_id}")

        except Exception as e:
            print(f" Failed to save emergency event: {e}")

    def process_frame(self, frame):
        """Process a single frame for pose-based fall detection"""
        self.frame_count += 1

        # Update FPS tracking
        now = time.time()
        dt = max(1e-3, now - self.last_ts)
        self.fps = 0.9 * self.fps + 0.1 * (1.0 / dt)
        self.last_ts = now

        # Update frame-based thresholds
        self.fall_duration_frames = max(3, int(self.fps * 0.8))
        self.still_frames_needed = max(6, int(self.fps * 1.0))

        # Run YOLO pose detection with tracking
        if self.use_tracking:
            results = self.model.track(
                source=frame,
                persist=True,  # keep IDs across frames
                imgsz=self.imgsz,
                verbose=False,
                tracker=self.tracker_cfg,
            )
        else:
            results = self.model(frame, imgsz=self.imgsz, verbose=False)

        person_count = 0
        max_severity = self.max_severity  # Keep previous max severity
        detections = []

        for r in results:
            kps = getattr(r, "keypoints", None)
            boxes = r.boxes
            if kps is None or boxes is None:
                continue

            # Get tracking IDs if available
            ids = (
                boxes.id.int().cpu().tolist()
                if getattr(boxes, "id", None) is not None
                else None
            )

            for i, box in enumerate(boxes):
                cls_id = int(box.cls)
                if cls_id != 0:  # person only
                    continue

                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                w, h = x2 - x1, y2 - y1
                if w < 50 or h < 100:  # keep min-body filter
                    continue

                # === Pose keypoints ===
                kp = kps.xy[0][i].cpu().numpy()  # shape (17, 2) for COCO
                # Indexes: 5=left_shoulder, 6=right_shoulder, 11=left_hip, 12=right_hip
                ls, rs, lh, rh = kp[5], kp[6], kp[11], kp[12]
                shoulder_mid = ((ls[0] + rs[0]) / 2.0, (ls[1] + rs[1]) / 2.0)
                hip_mid = ((lh[0] + rh[0]) / 2.0, (lh[1] + rh[1]) / 2.0)

                # Torso vector and angle to vertical
                vx, vy = (hip_mid[0] - shoulder_mid[0], hip_mid[1] - shoulder_mid[1])
                torso_len = max(1.0, np.hypot(vx, vy))
                angle_to_vertical = np.degrees(
                    np.arctan2(abs(vx), abs(vy))
                )  # 0=vertical, 90=horizontal

                # Track hip midpoint for normalized vertical velocity
                pid = (
                    ids[i] if ids else (i + 1)
                )  # deterministic id per frame if not tracking

                # Legacy compatibility
                self.person_head_positions.setdefault(pid, [])
                self.person_head_positions[pid].append(int(y1))

                self.person_center_positions.setdefault(pid, [])
                self.person_center_positions[pid].append(hip_mid)

                # Normalized vertical velocity: dy / torso_len (down is +)
                v_norm = 0.0
                hist = self.person_center_positions[pid]
                if len(hist) >= 2:
                    dy = hist[-1][1] - hist[-2][1]
                    v_norm = float(dy / torso_len)

                # Keep a short window for smoothing
                if len(hist) > 20:
                    self.person_center_positions[pid] = hist[-20:]

                # Apply EMA smoothing
                v_norm = self.ema("ema_vnorm", pid, v_norm, 0.25)
                angle_to_vertical = self.ema("ema_angle", pid, angle_to_vertical, 0.2)

                # Ground/lying detection
                H = frame.shape[0]
                near_floor = (max(y1, y2) > 0.85 * H) or (hip_mid[1] > 0.80 * H)

                # State machine pattern analysis
                pattern_score = self.analyze_temporal_pattern(
                    pid, v_norm, angle_to_vertical
                )

                # Legacy velocity calculation for compatibility
                velocity, acceleration = self.calculate_velocity(
                    pid, (int((x1 + x2) / 2), int((y1 + y2) / 2)), (w, h)
                )
                # Overwrite with normalized vertical velocity for robustness
                velocity = max(
                    velocity, v_norm * 10.0
                )  # bring to similar scale as thresholds

                # Recompute 'angle' from torso
                angle = angle_to_vertical
                angular_velocity = 0.0
                prev_angles = self.person_angles.setdefault(pid, [])
                if prev_angles:
                    angular_velocity = angle - prev_angles[-1]
                prev_angles.append(angle)
                self.person_angles[pid] = prev_angles[-15:]

                # Enhanced severity assessment with pose-based features
                severity = self.assess_severity_pose(
                    velocity,
                    angle,
                    pid,
                    v_norm,
                    angle_to_vertical,
                    pattern_score,
                    near_floor,
                )
                max_severity = max(max_severity, severity)

                person_count += 1

                # Store detection data
                detections.append(
                    {
                        "id": pid,
                        "bbox": [int(x1), int(y1), int(x2), int(y2)],
                        "center": [int((x1 + x2) / 2), int((y1 + y2) / 2)],
                        "velocity": float(velocity),
                        "angle": float(angle),
                        "severity": severity,
                        "v_norm": float(v_norm),
                        "torso_angle": float(angle_to_vertical),
                        "pattern_score": float(pattern_score),
                        "near_floor": near_floor,
                    }
                )

                # Draw bounding box and pose info
                color = (
                    (0, 255, 0)
                    if severity < self.emergency_severity_threshold
                    else (0, 0, 255)
                )
                cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)

                # Draw torso line
                cv2.line(
                    frame,
                    (int(shoulder_mid[0]), int(shoulder_mid[1])),
                    (int(hip_mid[0]), int(hip_mid[1])),
                    (255, 0, 0),
                    2,
                )

                # Add enhanced text info
                info_text = f"P{pid}: S{severity}/10 V{v_norm:.2f} A{angle_to_vertical:.0f}deg P{pattern_score:.1f}"
                if near_floor:
                    info_text += " FLOOR"
                cv2.putText(
                    frame,
                    info_text,
                    (int(x1), int(y1) - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    color,
                    1,
                )

        # Update statistics
        self.current_people_count = person_count
        self.max_severity = max_severity
        self.total_detections += 1

        # Check for emergency
        emergency_data = None
        if max_severity >= self.emergency_severity_threshold:
            if not self.emergency_active:
                self.emergency_active = True
                self.emergency_start_time = time.time()
                emergency_data = {
                    "type": "emergency_alert",
                    "severity": max_severity,
                    "message": f"Fall detected with severity {max_severity}/10",
                    "verification_time": self.verification_time,
                }
            else:
                # Check if verification period is complete
                elapsed_time = time.time() - self.emergency_start_time
                if elapsed_time >= self.verification_time:
                    self.total_emergencies += 1
                    emergency_data = {
                        "type": "emergency_verified",
                        "severity": max_severity,
                        "message": f"Emergency verified! Calling emergency services!",
                    }

                    # Store emergency image and event
                    video_url = self.store_emergency_video(frame)
                    if video_url:
                        # Get average velocity and angle from detections
                        avg_velocity = (
                            sum([d["velocity"] for d in detections]) / len(detections)
                            if detections
                            else 0
                        )
                        avg_angle = (
                            sum([d["angle"] for d in detections]) / len(detections)
                            if detections
                            else 0
                        )
                        self.save_emergency_event(
                            max_severity, avg_velocity, avg_angle, video_url
                        )

                        # Analyze with Gemini AI in background thread
                        if gemini_analyzer:
                            self.last_emergency_data = {
                                "severity": max_severity,
                                "velocity": avg_velocity,
                                "angle": avg_angle,
                                "timestamp": datetime.now().isoformat(),
                            }
                            threading.Thread(
                                target=self.analyze_with_gemini,
                                args=(frame, max_severity, avg_velocity, avg_angle),
                                daemon=True,
                            ).start()

                    # Reset emergency state
                    self.emergency_active = False
                    self.emergency_start_time = None
                else:
                    remaining_time = self.verification_time - elapsed_time
                    emergency_data = {
                        "type": "emergency_verifying",
                        "severity": max_severity,
                        "message": f"Emergency verification: {remaining_time:.1f}s remaining...",
                        "remaining_time": remaining_time,
                    }
        else:
            if self.emergency_active:
                self.emergency_active = False
                self.emergency_start_time = None
                emergency_data = {
                    "type": "emergency_cleared",
                    "message": "Emergency cleared - person movement normal",
                }

        # Add frame info
        cv2.putText(
            frame,
            f"Frame: {self.frame_count}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2,
        )
        cv2.putText(
            frame,
            f"People: {person_count}",
            (10, 70),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2,
        )
        cv2.putText(
            frame,
            f"Max Severity: {max_severity}/10",
            (10, 110),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2,
        )
        cv2.putText(
            frame,
            f"FPS: {self.fps:.1f}",
            (10, 150),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2,
        )

        if self.emergency_active:
            cv2.putText(
                frame,
                "EMERGENCY ACTIVE",
                (10, 190),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 0, 255),
                2,
            )

        # Store last frame
        self.last_frame = frame

        return frame, detections, emergency_data

    def start_camera(self):
        """Start camera detection with retries and better backend handling"""
        if self.camera_active:
            return False

        # Try different backends for better compatibility
        tried = []
        for params in [(0, None), (0, cv2.CAP_DSHOW), (0, cv2.CAP_AVFOUNDATION)]:
            idx, backend = params
            tried.append(params)

            if backend is not None:
                self.cap = cv2.VideoCapture(idx, backend)
            else:
                self.cap = cv2.VideoCapture(idx)

            if self.cap.isOpened():
                # Set sane properties
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                self.cap.set(cv2.CAP_PROP_FPS, 30)
                self.camera_active = True
                print(f"Camera opened successfully with backend: {backend}")
                break
            else:
                self.cap.release()

        if not self.camera_active:
            print(f"Camera open failed. Tried: {tried}")
            return False

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
        _, buffer = cv2.imencode(".jpg", self.last_frame)
        frame_base64 = base64.b64encode(buffer).decode("utf-8")
        return frame_base64

    # def upload_frame_to_s3(self, frame):
    #     """Save frame to file"""
    #     uuid = str(uuid.uuid4())
    #     s3 = self.aws_services['s3']
    #     s3.upload_fileobj(frame, os.getenv('AWS_S3_CATCH_BUCKET'), f'fall_detection/{uuid}.jpg')
    #     print(f" Frame uploaded to {os.getenv('AWS_S3_CATCH_BUCKET')}/fall_detection/{uuid}.jpg")
    #     return uuid

    def analyze_with_gemini(self, frame, severity, velocity, angle):
        """Analyze emergency with Gemini AI (runs in background)"""
        try:
            print(f" Analyzing fall with Gemini AI (Severity: {severity}/10)...")

            # Convert frame to base64
            _, buffer = cv2.imencode(".jpg", frame)
            frame_base64 = base64.b64encode(buffer).decode("utf-8")
            # uuid = self.upload_frame_to_s3(frame)
            # Analyze with Gemini
            result = gemini_analyzer.analyze_fall_image(
                frame_base64, severity=severity, velocity=velocity, angle=angle
            )

            if result.get("success"):
                self.last_ai_analysis = {
                    "analysis": result.get("analysis", ""),
                    "provider": result.get("provider", "Gemini AI"),
                    "timestamp": datetime.now().isoformat(),
                    "emergency_data": self.last_emergency_data,
                }
                print(f" Gemini analysis complete!")
            else:
                print(f"  Gemini analysis failed: {result.get('error', 'Unknown')}")
                self.last_ai_analysis = {
                    "error": result.get("error", "Analysis failed"),
                    "timestamp": datetime.now().isoformat(),
                }

        except Exception as e:
            print(f" Gemini analysis error: {e}")
            self.last_ai_analysis = {
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }


# Initialize fall detection backend
fall_detector = SimpleFallDetector()


# Flask routes
@app.route("/")
def index():
    return jsonify(
        {
            "message": "Fall Detection Backend API",
            "status": "running",
            "gemini_ai": (
                "enabled"
                if (gemini_analyzer and gemini_analyzer.api_key)
                else "disabled"
            ),
            "endpoints": {
                "/api/status": "GET - Get system status",
                "/api/start_camera": "POST - Start camera detection",
                "/api/stop_camera": "POST - Stop camera detection",
                "/api/latest_frame": "GET - Get latest camera frame",
                "/api/detections": "GET - Get latest detection data",
                "/api/ai_analysis": "GET - Get latest Gemini AI analysis",
                "/api/analyze_chat": "POST - Send chat message to Gemini AI",
            },
        }
    )


@app.route("/api/status")
def get_status():
    return jsonify(
        {
            "camera_active": fall_detector.camera_active,
            "aws_services": fall_detector.aws_services is not None,
            "stats": {
                "total_detections": fall_detector.total_detections,
                "total_emergencies": fall_detector.total_emergencies,
                "current_people_count": fall_detector.current_people_count,
                "max_severity": fall_detector.max_severity,
                "frame_count": fall_detector.frame_count,
            },
        }
    )


@app.route("/api/start_camera", methods=["POST"])
def start_camera():
    success = fall_detector.start_camera()
    return jsonify({"success": success})


@app.route("/api/stop_camera", methods=["POST"])
def stop_camera():
    success = fall_detector.stop_camera()
    return jsonify({"success": success})


@app.route("/api/latest_frame")
def get_latest_frame():
    frame_base64 = fall_detector.get_latest_frame()
    if frame_base64:
        return jsonify({"frame": frame_base64, "timestamp": datetime.now().isoformat()})
    else:
        return jsonify({"error": "No frame available"}), 404


@app.route("/api/detections")
def get_detections():
    return jsonify(
        {
            "detections": fall_detector.person_positions,
            "stats": {
                "total_detections": fall_detector.total_detections,
                "total_emergencies": fall_detector.total_emergencies,
                "current_people_count": fall_detector.current_people_count,
                "max_severity": fall_detector.max_severity,
                "emergency_active": fall_detector.emergency_active,
            },
        }
    )


@app.route("/api/ai_analysis")
def get_ai_analysis():
    """Get the latest AI analysis from Gemini"""
    if fall_detector.last_ai_analysis:
        return jsonify(fall_detector.last_ai_analysis)
    else:
        return jsonify(
            {
                "message": "No AI analysis available yet",
                "gemini_configured": gemini_analyzer is not None
                and gemini_analyzer.api_key is not None,
            }
        )


@app.route("/api/analyze_chat", methods=["POST"])
def analyze_chat():
    """Send a chat message to Gemini API"""
    if not gemini_analyzer or not gemini_analyzer.api_key:
        return (
            jsonify(
                {
                    "error": "Gemini API not configured",
                    "setup_instructions": "Set GOOGLE_API_KEY in .env file",
                }
            ),
            400,
        )

    data = request.json
    message = data.get("message", "")

    if not message:
        return jsonify({"error": "No message provided"}), 400

    try:
        # Use Gemini for chat-style analysis
        import requests as req

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={gemini_analyzer.api_key}"

        payload = {
            "contents": [{"parts": [{"text": message}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 2048},
        }

        response = req.post(url, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()

        if "candidates" in result and len(result["candidates"]) > 0:
            candidate = result["candidates"][0]
            if "content" in candidate and "parts" in candidate["content"]:
                analysis = candidate["content"]["parts"][0]["text"]
            else:
                analysis = str(candidate)
        else:
            analysis = str(result)

        return jsonify(
            {
                "success": True,
                "response": analysis,
                "timestamp": datetime.now().isoformat(),
            }
        )

    except Exception as e:
        return jsonify({"error": str(e), "type": type(e).__name__}), 500


if __name__ == "__main__":
    print(" Starting Simple Fall Detection Backend")
    print("=" * 50)
    print(" Features:")
    print("   - Real-time camera detection")
    print("   - REST API endpoints")
    print("   - AWS services integration")
    if gemini_analyzer and gemini_analyzer.api_key:
        print("   -  Gemini AI Analysis (ACTIVE)")
    else:
        print("   -  Gemini AI (not configured)")
        print("     Set GOOGLE_API_KEY in .env to enable")
    print("")
    print(" Server will be available at:")
    print("   - HTTP: http://localhost:5001")
    print("")
    print(" Available endpoints:")
    print("   - GET  /api/status")
    print("   - POST /api/start_camera")
    print("   - POST /api/stop_camera")
    print("   - GET  /api/latest_frame")
    print("   - GET  /api/detections")
    print("   - GET  /api/ai_analysis  (Gemini AI)")
    print("   - POST /api/analyze_chat (Gemini Chat)")
    print("")

    app.run(debug=True, host="0.0.0.0", port=5001)
