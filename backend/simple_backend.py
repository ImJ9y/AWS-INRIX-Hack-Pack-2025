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
        self.model = YOLO("yolov8n.pt")
        self.aws_services = self.init_aws_services()
        self.fall_threshold_velocity = float(os.getenv('FALL_THRESHOLD_VELOCITY', '0.5'))  # Less sensitive - only real falls
        self.fall_threshold_angle = float(os.getenv('FALL_THRESHOLD_ANGLE', '60'))  # Less sensitive - only sharp angles
        self.emergency_severity_threshold = int(os.getenv('EMERGENCY_SEVERITY_THRESHOLD', '7'))  # Only real emergencies
        self.verification_time = float(os.getenv('VERIFICATION_TIME_SECONDS', '5.0'))
        
        # Fall detection state
        self.person_positions = {}
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
    
    def calculate_velocity(self, person_id, new_position):
        """Calculate velocity of person movement"""
        if person_id not in self.person_positions:
            self.person_positions[person_id] = []
        
        self.person_positions[person_id].append(new_position)
        
        # Keep only last 5 positions
        if len(self.person_positions[person_id]) > 5:
            self.person_positions[person_id] = self.person_positions[person_id][-5:]
        
        if len(self.person_positions[person_id]) < 2:
            return 0.0
        
        # Calculate velocity (pixels per frame)
        positions = self.person_positions[person_id]
        dx = positions[-1][0] - positions[-2][0]
        dy = positions[-1][1] - positions[-2][1]
        velocity = np.sqrt(dx*dx + dy*dy)
        
        return velocity
    
    def calculate_angle(self, person_id):
        """Calculate body angle (simplified)"""
        if person_id not in self.person_positions or len(self.person_positions[person_id]) < 2:
            return 0.0
        
        positions = self.person_positions[person_id]
        if len(positions) < 2:
            return 0.0
        
        # Simple angle calculation based on movement direction
        dx = positions[-1][0] - positions[-2][0]
        dy = positions[-1][1] - positions[-2][1]
        
        if dx == 0:
            return 90.0 if dy > 0 else 0.0
        
        angle = np.degrees(np.arctan(abs(dy) / abs(dx)))
        return angle
    
    def assess_severity(self, velocity, angle):
        """Assess fall severity (1-10 scale)"""
        severity = 1
        
        # Velocity component (0-5 points) - less sensitive
        # Only trigger on significant velocity changes (actual falls)
        if velocity > self.fall_threshold_velocity:
            # More gradual increase for velocity
            excess_velocity = velocity - self.fall_threshold_velocity
            severity += min(5, int(excess_velocity * 5))  # Reduced multiplier
        
        # Angle component (0-5 points) - less sensitive
        # Only trigger on sharp angles (actual falls)
        if angle > self.fall_threshold_angle:
            # More gradual increase for angle
            excess_angle = angle - self.fall_threshold_angle
            severity += min(5, int(excess_angle / 15))  # Less sensitive
        
        return min(10, severity)
    
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
        max_severity = 1
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
                            
                            # Calculate velocity and angle
                            velocity = self.calculate_velocity(person_count, (center_x, center_y))
                            angle = self.calculate_angle(person_count)
                            
                            # Assess severity
                            severity = self.assess_severity(velocity, angle)
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
