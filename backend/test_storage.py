#!/usr/bin/env python3
"""
Test Storage Implementation
Manually triggers storage to verify S3 and DynamoDB are working
"""
import cv2
import numpy as np
import time
from simple_backend import SimpleFallDetector
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_storage():
    """Test the storage implementation"""
    print("🧪 Testing Storage Implementation")
    print("=" * 60)
    
    # Initialize detector
    detector = SimpleFallDetector()
    
    if not detector.aws_services:
        print("❌ AWS services not available")
        return False
    
    print("✅ AWS services initialized")
    
    # Create a test frame
    print("\n📸 Creating test frame...")
    test_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(test_frame, "TEST EMERGENCY", (50, 240), 
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)
    print("✅ Test frame created")
    
    # Test S3 storage
    print("\n📹 Testing S3 storage...")
    try:
        video_url = detector.store_emergency_video(test_frame)
        if video_url:
            print(f"✅ S3 storage successful: {video_url}")
        else:
            print("⚠️ S3 storage returned None")
            return False
    except Exception as e:
        print(f"❌ S3 storage failed: {e}")
        return False
    
    # Test DynamoDB storage
    print("\n📊 Testing DynamoDB storage...")
    try:
        detector.save_emergency_event(
            severity=9,
            velocity=0.8,
            angle=75.0,
            video_url=video_url
        )
        print("✅ DynamoDB storage successful")
    except Exception as e:
        print(f"❌ DynamoDB storage failed: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("✅ All storage tests passed!")
    print("=" * 60)
    
    print("\n💡 You can now view the stored data:")
    print("   python3 view_emergency_images.py")
    print("   python3 view_stored_data.py")
    
    return True

if __name__ == "__main__":
    test_storage()

