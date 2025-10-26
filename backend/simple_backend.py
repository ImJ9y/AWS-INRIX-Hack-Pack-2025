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
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), 'analyze_fall'))

# Load environment variables
load_dotenv()

# Import Gemini analyzer
try:
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from analyze_fall.analyze import EmergencyImageAnalyzer
    gemini_analyzer = EmergencyImageAnalyzer()
    print("✅ Gemini AI Analyzer loaded")
except Exception as e:
    print(f"⚠️  Gemini analyzer not available: {e}")
    gemini_analyzer = None

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

class SimpleFallDetector:
    def __init__(self):
        self.model = YOLO("yolov8n.pt")
        self.aws_services = self.init_aws_services()
        self.fall_threshold_velocity = float(os.getenv('FALL_THRESHOLD_VELOCITY', '3.0'))  # Detect falls from any angle
        self.fall_threshold_angle = float(os.getenv('FALL_THRESHOLD_ANGLE', '30'))  # More sensitive - detect all types of falls
        self.emergency_severity_threshold = int(os.getenv('EMERGENCY_SEVERITY_THRESHOLD', '6'))  # Detect moderate falls
        self.verification_time = float(os.getenv('VERIFICATION_TIME_SECONDS', '5.0'))
        
        # Fall detection state
        self.person_positions = {}
        self.person_velocities = {}  # Track velocity history
        self.person_angles = {}  # Track angle history
        self.person_sizes = {}  # Track bounding box sizes (for position in frame)
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
                's3': boto3.client('s3'),
                'dynamodb': boto3.resource('dynamodb'),
                'sns': boto3.client('sns'),
                'cloudwatch': boto3.client('cloudwatch')
            }
        except Exception as e:
            print(f"⚠️ AWS services not available: {e}")
            return None
    
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
            dx = positions[-i][0] - positions[-i-1][0]
            dy = positions[-i][1] - positions[-i-1][1]
            
            # Normalize by frame time (assuming ~30 FPS)
            dt = 1.0  # 1 frame
            vx = dx / dt
            vy = dy / dt
            
            # Weight downward movement heavily (falling)
            if vy > 0:  # Moving down
                velocity = np.sqrt(vx*vx + vy*vy * 3.0)  # Weight downward 3x
            else:  # Moving up (unlikely to be fall)
                velocity = np.sqrt(vx*vx + vy*vy) * 0.3
            
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
        if person_id not in self.person_positions or len(self.person_positions[person_id]) < 4:
            return 0.0
        
        positions = self.person_positions[person_id]
        
        # Calculate angles from multiple frame pairs for stability
        angles = []
        
        # Analyze last 4 frames
        for i in range(1, min(4, len(positions))):
            dx = positions[-i][0] - positions[-i-1][0]
            dy = positions[-i][1] - positions[-i-1][1]
            
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
                velocity_score = ((velocity - self.fall_threshold_velocity) / 
                                 (max_velocity - self.fall_threshold_velocity)) * 4 * velocity_trend
            
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
                angle_score = ((angle - self.fall_threshold_angle) / 
                              (max_angle - self.fall_threshold_angle)) * 4 * angle_trend
            
            severity += min(4, int(angle_score))
        
        # Bonus point if both indicators are present (definite fall)
        if velocity > self.fall_threshold_velocity and angle > self.fall_threshold_angle:
            severity += 1
        
        # Bonus point if very high velocity (rapid fall)
        if velocity > self.fall_threshold_velocity * 3:
            severity += 1
        
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
        """Process a single frame for fall detection"""
        self.frame_count += 1
        
        # Run YOLO detection
        results = self.model(frame, verbose=False)
        
        person_count = 0
        max_severity = self.max_severity  # Keep previous max severity
        detections = []
        
        for r in results:
            boxes = r.boxes
            if boxes is not None:
                for box in boxes:
                    if int(box.cls) == 0:  # person class (whole body)
                        # Check if it's a full body detection (not just face)
                        # In YOLO, person class detects whole body, but we can filter by size
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                        width = x2 - x1
                        height = y2 - y1
                        
                        # Only process if it's a reasonable sized detection (full body)
                        # Filters out tiny face detections
                        if width > 50 and height > 100:  # Minimum body size
                            person_count += 1
                            
                            # Get person position (center of bounding box)
                            center_x = int((x1 + x2) / 2)
                            center_y = int((y1 + y2) / 2)
                            box_size = (width, height)
                            
                            # Calculate velocity and angle
                            velocity = self.calculate_velocity(person_count, (center_x, center_y), box_size)
                            angle = self.calculate_angle(person_count)
                            
                            # Assess severity with person_id for trend analysis
                            severity = self.assess_severity(velocity, angle, person_count)
                            max_severity = max(max_severity, severity)
                            
                            # Store detection data
                            detections.append({
                                'id': person_count,
                                'bbox': [int(x1), int(y1), int(x2), int(y2)],
                                'center': [center_x, center_y],
                                'velocity': float(velocity),
                                'angle': float(angle),
                                'severity': severity
                            })
                            
                            # Draw bounding box and info
                            color = (0, 255, 0) if severity < self.emergency_severity_threshold else (0, 0, 255)
                            cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
                            
                            # Add text info
                            info_text = f"Person {person_count}: S{severity}/10 V{velocity:.2f} A{angle:.1f}°"
                            cv2.putText(frame, info_text, (int(x1), int(y1)-10), 
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        
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
                    'type': 'emergency_alert',
                    'severity': max_severity,
                    'message': f'Fall detected with severity {max_severity}/10',
                    'verification_time': self.verification_time
                }
            else:
                # Check if verification period is complete
                elapsed_time = time.time() - self.emergency_start_time
                if elapsed_time >= self.verification_time:
                    self.total_emergencies += 1
                    emergency_data = {
                        'type': 'emergency_verified',
                        'severity': max_severity,
                        'message': f'Emergency verified! Calling emergency services!'
                    }
                    
                    # Store emergency image and event
                    video_url = self.store_emergency_video(frame)
                    if video_url:
                        # Get average velocity and angle from detections
                        avg_velocity = sum([d['velocity'] for d in detections]) / len(detections) if detections else 0
                        avg_angle = sum([d['angle'] for d in detections]) / len(detections) if detections else 0
                        self.save_emergency_event(max_severity, avg_velocity, avg_angle, video_url)
                        
                        # Analyze with Gemini AI in background thread
                        if gemini_analyzer:
                            self.last_emergency_data = {
                                'severity': max_severity,
                                'velocity': avg_velocity,
                                'angle': avg_angle,
                                'timestamp': datetime.now().isoformat()
                            }
                            threading.Thread(
                                target=self.analyze_with_gemini,
                                args=(frame, max_severity, avg_velocity, avg_angle),
                                daemon=True
                            ).start()
                    
                    # Reset emergency state
                    self.emergency_active = False
                    self.emergency_start_time = None
                else:
                    remaining_time = self.verification_time - elapsed_time
                    emergency_data = {
                        'type': 'emergency_verifying',
                        'severity': max_severity,
                        'message': f'Emergency verification: {remaining_time:.1f}s remaining...',
                        'remaining_time': remaining_time
                    }
        else:
            if self.emergency_active:
                self.emergency_active = False
                self.emergency_start_time = None
                emergency_data = {
                    'type': 'emergency_cleared',
                    'message': 'Emergency cleared - person movement normal'
                }
        
        # Add frame info
        cv2.putText(frame, f"Frame: {self.frame_count}", (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.putText(frame, f"People: {person_count}", (10, 70), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.putText(frame, f"Max Severity: {max_severity}/10", (10, 110), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        
        if self.emergency_active:
            cv2.putText(frame, "EMERGENCY ACTIVE", (10, 150), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        
        # Store last frame
        self.last_frame = frame
        
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
    
    def analyze_with_gemini(self, frame, severity, velocity, angle):
        """Analyze emergency with Gemini AI (runs in background)"""
        try:
            print(f"🤖 Analyzing fall with Gemini AI (Severity: {severity}/10)...")
            
            # Convert frame to base64
            _, buffer = cv2.imencode('.jpg', frame)
            frame_base64 = base64.b64encode(buffer).decode('utf-8')
            
            # Analyze with Gemini
            result = gemini_analyzer.analyze_fall_image(
                frame_base64,
                severity=severity,
                velocity=velocity,
                angle=angle
            )
            
            if result.get('success'):
                self.last_ai_analysis = {
                    'analysis': result.get('analysis', ''),
                    'provider': result.get('provider', 'Gemini AI'),
                    'timestamp': datetime.now().isoformat(),
                    'emergency_data': self.last_emergency_data
                }
                print(f"✅ Gemini analysis complete!")
            else:
                print(f"⚠️  Gemini analysis failed: {result.get('error', 'Unknown')}")
                self.last_ai_analysis = {
                    'error': result.get('error', 'Analysis failed'),
                    'timestamp': datetime.now().isoformat()
                }
                
        except Exception as e:
            print(f"❌ Gemini analysis error: {e}")
            self.last_ai_analysis = {
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }

# Initialize fall detection backend
fall_detector = SimpleFallDetector()

# Flask routes
@app.route('/')
def index():
    return jsonify({
        'message': 'Fall Detection Backend API',
        'status': 'running',
        'gemini_ai': 'enabled' if (gemini_analyzer and gemini_analyzer.api_key) else 'disabled',
        'endpoints': {
            '/api/status': 'GET - Get system status',
            '/api/start_camera': 'POST - Start camera detection',
            '/api/stop_camera': 'POST - Stop camera detection',
            '/api/latest_frame': 'GET - Get latest camera frame',
            '/api/detections': 'GET - Get latest detection data',
            '/api/ai_analysis': 'GET - Get latest Gemini AI analysis',
            '/api/analyze_chat': 'POST - Send chat message to Gemini AI'
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
    return jsonify({
        'detections': fall_detector.person_positions,
        'stats': {
            'total_detections': fall_detector.total_detections,
            'total_emergencies': fall_detector.total_emergencies,
            'current_people_count': fall_detector.current_people_count,
            'max_severity': fall_detector.max_severity,
            'emergency_active': fall_detector.emergency_active
        }
    })

@app.route('/api/ai_analysis')
def get_ai_analysis():
    """Get the latest AI analysis from Gemini"""
    if fall_detector.last_ai_analysis:
        return jsonify(fall_detector.last_ai_analysis)
    else:
        return jsonify({
            'message': 'No AI analysis available yet',
            'gemini_configured': gemini_analyzer is not None and gemini_analyzer.api_key is not None
        })

@app.route('/api/analyze_chat', methods=['POST'])
def analyze_chat():
    """Send a chat message to Gemini API"""
    if not gemini_analyzer or not gemini_analyzer.api_key:
        return jsonify({
            'error': 'Gemini API not configured',
            'setup_instructions': 'Set GOOGLE_API_KEY in .env file'
        }), 400
    
    data = request.json
    message = data.get('message', '')
    
    if not message:
        return jsonify({'error': 'No message provided'}), 400
    
    try:
        # Use Gemini for chat-style analysis
        import requests as req
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={gemini_analyzer.api_key}"
        
        payload = {
            "contents": [{
                "parts": [{"text": message}]
            }],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 2048
            }
        }
        
        response = req.post(url, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        
        if 'candidates' in result and len(result['candidates']) > 0:
            candidate = result['candidates'][0]
            if 'content' in candidate and 'parts' in candidate['content']:
                analysis = candidate['content']['parts'][0]['text']
            else:
                analysis = str(candidate)
        else:
            analysis = str(result)
        
        return jsonify({
            'success': True,
            'response': analysis,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'error': str(e),
            'type': type(e).__name__
        }), 500

if __name__ == '__main__':
    print("🚀 Starting Simple Fall Detection Backend")
    print("=" * 50)
    print("✅ Features:")
    print("   • Real-time camera detection")
    print("   • REST API endpoints")
    print("   • AWS services integration")
    if gemini_analyzer and gemini_analyzer.api_key:
        print("   • 🤖 Gemini AI Analysis (ACTIVE)")
    else:
        print("   • ⚠️  Gemini AI (not configured)")
        print("     Set GOOGLE_API_KEY in .env to enable")
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
    print("   • GET  /api/ai_analysis  (Gemini AI)")
    print("   • POST /api/analyze_chat (Gemini Chat)")
    print("")
    
    app.run(debug=True, host='0.0.0.0', port=5001)
