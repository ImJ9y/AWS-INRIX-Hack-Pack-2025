#!/usr/bin/env python3
"""
Quick AWS Integration Test
Tests all AWS services used in the fall detection demo
"""
import os
import boto3
import json
import uuid
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_aws_services():
    print("🧪 AWS Integration Test")
    print("=" * 30)
    
    # Initialize AWS services
    try:
        s3 = boto3.client('s3')
        dynamodb = boto3.resource('dynamodb')
        sns = boto3.client('sns')
        cloudwatch = boto3.client('cloudwatch')
        print("✅ AWS services initialized")
    except Exception as e:
        print(f"❌ Failed to initialize AWS services: {e}")
        return False
    
    # Test S3
    print("\n🗄️ Testing S3...")
    try:
        bucket_name = os.getenv('AWS_S3_EMERGENCY_BUCKET', 'fall-detection-emergency-data-dev-800680963266')
        # Create a test file
        test_content = f"Test emergency data - {datetime.now().isoformat()}"
        test_key = f"test/emergency_test_{uuid.uuid4().hex[:8]}.txt"
        
        s3.put_object(
            Bucket=bucket_name,
            Key=test_key,
            Body=test_content,
            ContentType='text/plain'
        )
        print(f"   ✅ S3 upload successful: s3://{bucket_name}/{test_key}")
        
        # Clean up test file
        s3.delete_object(Bucket=bucket_name, Key=test_key)
        print("   ✅ S3 cleanup successful")
        
    except Exception as e:
        print(f"   ❌ S3 test failed: {e}")
        return False
    
    # Test DynamoDB
    print("\n📊 Testing DynamoDB...")
    try:
        table_name = os.getenv('AWS_DYNAMODB_EVENTS_TABLE', 'fall-detection-events-dev')
        table = dynamodb.Table(table_name)
        
        # Create test item
        test_item = {
            'event_id': str(uuid.uuid4()),
            'timestamp': datetime.now().isoformat(),
            'severity': 8,
            'velocity': 0.5,
            'angle': 70.0,
            'video_url': 'test-url',
            'status': 'test',
            'ttl': int(datetime.now().timestamp()) + 3600  # 1 hour
        }
        
        table.put_item(Item=test_item)
        print(f"   ✅ DynamoDB put successful: {test_item['event_id']}")
        
        # Clean up test item
        table.delete_item(
            Key={
                'event_id': test_item['event_id'],
                'timestamp': test_item['timestamp']
            }
        )
        print("   ✅ DynamoDB cleanup successful")
        
    except Exception as e:
        print(f"   ❌ DynamoDB test failed: {e}")
        return False
    
    # Test SNS
    print("\n📢 Testing SNS...")
    try:
        topic_arn = os.getenv('AWS_SNS_EMERGENCY_TOPIC_ARN', 'arn:aws:sns:us-east-1:800680963266:fall-detection-emergency-dev')
        
        test_message = {
            'default': 'AWS Integration Test - Fall Detection System',
            'sms': '🧪 Test: Fall Detection AWS Integration Working!',
            'email': f'AWS Integration Test\n\nTime: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\nStatus: All services working correctly!'
        }
        
        sns.publish(
            TopicArn=topic_arn,
            Message=json.dumps(test_message),
            Subject='Fall Detection AWS Integration Test'
        )
        print("   ✅ SNS publish successful")
        
    except Exception as e:
        print(f"   ❌ SNS test failed: {e}")
        return False
    
    # Test CloudWatch
    print("\n📈 Testing CloudWatch...")
    try:
        namespace = os.getenv('AWS_CLOUDWATCH_METRICS_NAMESPACE', 'FallDetectionSystem')
        
        cloudwatch.put_metric_data(
            Namespace=namespace,
            MetricData=[
                {
                    'MetricName': 'IntegrationTest',
                    'Value': 1,
                    'Unit': 'Count',
                    'Dimensions': [
                        {
                            'Name': 'TestType',
                            'Value': 'AWSIntegration'
                        }
                    ]
                }
            ]
        )
        print("   ✅ CloudWatch metrics published")
        
    except Exception as e:
        print(f"   ❌ CloudWatch test failed: {e}")
        return False
    
    print("\n🎉 All AWS services working correctly!")
    print("✅ Your fall detection system is ready for demo!")
    return True

if __name__ == "__main__":
    test_aws_services()