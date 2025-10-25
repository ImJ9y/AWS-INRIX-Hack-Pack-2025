#!/usr/bin/env python3
"""
Environment Setup Script
Helps configure AWS credentials and test the system
"""
import os
import sys
from dotenv import load_dotenv

def check_environment():
    """Check if environment is properly configured"""
    print("🔍 Checking Environment Configuration")
    print("=" * 40)
    
    # Load config
    load_dotenv()
    
    # Check AWS credentials
    aws_key = os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret = os.getenv('AWS_SECRET_ACCESS_KEY')
    aws_region = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
    
    print(f"✅ AWS Region: {aws_region}")
    
    if aws_key and aws_key != 'your_aws_access_key_here':
        print(f"✅ AWS Access Key: {aws_key[:10]}...")
    else:
        print("❌ AWS Access Key: Not configured")
    
    if aws_secret and aws_secret != 'your_aws_secret_key_here':
        print(f"✅ AWS Secret Key: {aws_secret[:10]}...")
    else:
        print("❌ AWS Secret Key: Not configured")
    
    # Check AWS services
    s3_bucket = os.getenv('AWS_S3_EMERGENCY_BUCKET')
    dynamodb_table = os.getenv('AWS_DYNAMODB_EVENTS_TABLE')
    sns_topic = os.getenv('AWS_SNS_EMERGENCY_TOPIC_ARN')
    
    print(f"✅ S3 Bucket: {s3_bucket}")
    print(f"✅ DynamoDB Table: {dynamodb_table}")
    print(f"✅ SNS Topic: {sns_topic[:50]}...")
    
    # Check detection parameters
    fall_velocity = os.getenv('FALL_THRESHOLD_VELOCITY', '0.3')
    fall_angle = os.getenv('FALL_THRESHOLD_ANGLE', '45')
    severity_threshold = os.getenv('EMERGENCY_SEVERITY_THRESHOLD', '8')
    
    print(f"✅ Fall Velocity Threshold: {fall_velocity}")
    print(f"✅ Fall Angle Threshold: {fall_angle}°")
    print(f"✅ Emergency Severity Threshold: {severity_threshold}/10")
    
    return aws_key and aws_secret and aws_key != 'your_aws_access_key_here'

def test_imports():
    """Test if all required packages are installed"""
    print("\n📦 Testing Package Imports")
    print("=" * 30)
    
    packages = [
        ('cv2', 'opencv-python'),
        ('ultralytics', 'ultralytics'),
        ('numpy', 'numpy'),
        ('boto3', 'boto3'),
        ('flask', 'flask'),
        ('PIL', 'pillow'),
        ('dotenv', 'python-dotenv')
    ]
    
    all_good = True
    for package, pip_name in packages:
        try:
            __import__(package)
            print(f"✅ {package} ({pip_name})")
        except ImportError:
            print(f"❌ {package} ({pip_name}) - Run: pip install {pip_name}")
            all_good = False
    
    return all_good

def main():
    print("🚀 Fall Detection System - Environment Setup")
    print("=" * 50)
    
    # Test imports
    imports_ok = test_imports()
    
    # Check environment
    env_ok = check_environment()
    
    print("\n📋 Setup Summary")
    print("=" * 20)
    
    if imports_ok:
        print("✅ All required packages are installed")
    else:
        print("❌ Some packages are missing - run: pip install -r requirements.txt")
    
    if env_ok:
        print("✅ Environment is properly configured")
    else:
        print("❌ Environment needs configuration")
        print("\n🔧 To configure AWS credentials:")
        print("   1. Edit config.env file")
        print("   2. Replace 'your_aws_access_key_here' with your actual AWS Access Key")
        print("   3. Replace 'your_aws_secret_key_here' with your actual AWS Secret Key")
        print("   4. Add your session token if using temporary credentials")
    
    if imports_ok and env_ok:
        print("\n🎉 System is ready!")
        print("   Run: python simple_backend.py")
        print("   Then open: http://localhost:5173")
    else:
        print("\n⚠️  Please fix the issues above before running the system")

if __name__ == "__main__":
    main()
