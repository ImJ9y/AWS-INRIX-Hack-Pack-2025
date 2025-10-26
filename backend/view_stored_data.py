#!/usr/bin/env python3
"""
View Stored Data Script
Retrieves and displays data from all AWS storage locations
"""
import os
import boto3
import json
from datetime import datetime
from dotenv import load_dotenv
from decimal import Decimal

# Load environment variables
load_dotenv()

def convert_decimal_to_float(obj):
    """Convert Decimal to float for JSON serialization"""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: convert_decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimal_to_float(item) for item in obj]
    return obj

def view_dynamodb_events():
    """View events from DynamoDB"""
    print("\n" + "="*60)
    print(" DYNAMODB EVENTS TABLE")
    print("="*60)
    
    try:
        table_name = os.getenv('AWS_DYNAMODB_EVENTS_TABLE', 'fall-detection-events-dev')
        region = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        dynamodb = boto3.resource('dynamodb', region_name=region)
        table = dynamodb.Table(table_name)
        
        # Scan table (limit to 10 items)
        response = table.scan(Limit=10)
        items = response.get('Items', [])
        
        if items:
            print(f"\nFound {len(items)} recent events:\n")
            for item in items:
                item = convert_decimal_to_float(item)
                print(f"Event ID: {item.get('event_id')}")
                print(f"Timestamp: {item.get('timestamp')}")
                print(f"Severity: {item.get('severity', 0)}/10")
                print(f"Velocity: {item.get('velocity', 0)}")
                print(f"Angle: {item.get('angle', 0)}°")
                print(f"Status: {item.get('status', 'unknown')}")
                print("-" * 60)
        else:
            print("No events found in database")
            
    except Exception as e:
        print(f" Error accessing DynamoDB: {e}")

def view_analytics():
    """View analytics data"""
    print("\n" + "="*60)
    print("📈 ANALYTICS DATA")
    print("="*60)
    
    try:
        table_name = os.getenv('AWS_DYNAMODB_ANALYTICS_TABLE', 'fall-detection-analytics-dev')
        region = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        dynamodb = boto3.resource('dynamodb', region_name=region)
        table = dynamodb.Table(table_name)
        
        # Scan table (limit to 10 items)
        response = table.scan(Limit=10)
        items = response.get('Items', [])
        
        if items:
            print(f"\nFound {len(items)} analytics records:\n")
            for item in items:
                item = convert_decimal_to_float(item)
                print(f"Date/Hour: {item.get('date_hour')}")
                print(f"Camera ID: {item.get('camera_id', 'unknown')}")
                print(f"Total Detections: {item.get('total_detections', 0)}")
                print(f"Fall Count: {item.get('fall_count', 0)}")
                print(f"Emergency Count: {item.get('emergency_count', 0)}")
                print(f"Max Severity: {item.get('max_severity', 0)}/10")
                print("-" * 60)
        else:
            print("No analytics data found")
            
    except Exception as e:
        print(f" Error accessing analytics: {e}")

def view_s3_files():
    """View S3 bucket contents"""
    print("\n" + "="*60)
    print("🗄️ S3 BUCKET CONTENTS")
    print("="*60)
    
    try:
        bucket_name = os.getenv('AWS_S3_EMERGENCY_BUCKET', 'fall-detection-emergency-data-dev-800680963266')
        region = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        s3 = boto3.client('s3', region_name=region)
        
        # List objects in bucket (limit to 20)
        response = s3.list_objects_v2(Bucket=bucket_name, MaxKeys=20)
        
        if 'Contents' in response:
            print(f"\nFound {len(response['Contents'])} files:\n")
            for obj in response['Contents']:
                print(f"File: {obj['Key']}")
                print(f"Size: {obj['Size']} bytes")
                print(f"Last Modified: {obj['LastModified']}")
                print("-" * 60)
        else:
            print("No files found in S3 bucket")
            
    except Exception as e:
        print(f" Error accessing S3: {e}")

def view_emergency_tracking():
    """View emergency tracking data"""
    print("\n" + "="*60)
    print(" EMERGENCY TRACKING")
    print("="*60)
    
    try:
        table_name = os.getenv('AWS_DYNAMODB_TRACKING_TABLE', 'fall-detection-emergency-tracking-dev')
        region = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        dynamodb = boto3.resource('dynamodb', region_name=region)
        table = dynamodb.Table(table_name)
        
        # Scan table (limit to 10 items)
        response = table.scan(Limit=10)
        items = response.get('Items', [])
        
        if items:
            print(f"\nFound {len(items)} active emergencies:\n")
            for item in items:
                item = convert_decimal_to_float(item)
                print(f"Event ID: {item.get('event_id')}")
                print(f"Camera ID: {item.get('camera_id', 'unknown')}")
                print(f"Severity: {item.get('severity', 0)}/10")
                print(f"Response Level: {item.get('response_level', 'unknown')}")
                print(f"Status: {item.get('status', 'unknown')}")
                print(f"Timestamp: {item.get('timestamp')}")
                print("-" * 60)
        else:
            print("No active emergencies")
            
    except Exception as e:
        print(f" Error accessing emergency tracking: {e}")

def main():
    print("\n🔍 VIEWING STORED DATA FROM AWS SERVICES")
    print("="*60)
    print(f"Region: {os.getenv('AWS_DEFAULT_REGION', 'us-east-1')}")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # View all data sources
    view_dynamodb_events()
    view_analytics()
    view_s3_files()
    view_emergency_tracking()
    
    print("\n" + "="*60)
    print(" Data retrieval complete!")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
