#!/usr/bin/env python3
"""
View Emergency Images Script
Lists and displays emergency images stored in S3
"""
import os
import boto3
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def list_emergency_images():
    """List all emergency images in S3"""
    print("\n" + "="*70)
    print("📸 EMERGENCY IMAGES IN S3")
    print("="*70)
    
    try:
        bucket_name = os.getenv('AWS_S3_EMERGENCY_BUCKET')
        
        if not bucket_name:
            print("\n❌ Error: AWS_S3_EMERGENCY_BUCKET not configured")
            print("   Please create a .env file with your AWS configuration")
            print("   See .env for reference")
            return 0
        
        region = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        s3 = boto3.client('s3', region_name=region)
        
        print(f"\nBucket: {bucket_name}")
        print(f"Region: {region}")
        print(f"Path: emergency-images/")
        print("\n" + "-"*70)
        
        # List all emergency images
        paginator = s3.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=bucket_name, Prefix='emergency-images/')
        
        image_count = 0
        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    image_count += 1
                    key = obj['Key']
                    size = obj['Size']
                    last_modified = obj['LastModified']
                    
                    # Parse filename to show timestamp
                    filename = key.split('/')[-1]
                    
                    print(f"\n📷 Image #{image_count}")
                    print(f"   Filename: {filename}")
                    print(f"   Size: {size:,} bytes ({size/1024:.2f} KB)")
                    print(f"   Uploaded: {last_modified.strftime('%Y-%m-%d %H:%M:%S')}")
                    print(f"   S3 Path: s3://{bucket_name}/{key}")
                    
                    # Generate presigned URL (valid for 1 hour)
                    try:
                        url = s3.generate_presigned_url(
                            'get_object',
                            Params={'Bucket': bucket_name, 'Key': key},
                            ExpiresIn=3600
                        )
                        print(f"   View URL: {url}")
                    except Exception as e:
                        print(f"   View URL: Could not generate (check permissions)")
                    
                    print("-" * 70)
        
        if image_count == 0:
            print("\n⚠️  No emergency images found in S3 bucket")
            print("   Images will appear here after fall detection events")
        else:
            print(f"\n✅ Found {image_count} emergency image(s)")
        
        return image_count
        
    except Exception as e:
        print(f"❌ Error accessing S3: {e}")
        return 0

def download_latest_image():
    """Download the most recent emergency image"""
    try:
        bucket_name = os.getenv('AWS_S3_EMERGENCY_BUCKET')
        region = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        s3 = boto3.client('s3', region_name=region)
        
        # Get the most recent image
        response = s3.list_objects_v2(
            Bucket=bucket_name,
            Prefix='emergency-images/',
            MaxKeys=1
        )
        
        if 'Contents' not in response or len(response['Contents']) == 0:
            print("\n⚠️  No emergency images available to download")
            return None
        
        # Sort by last modified to get the latest
        images = sorted(response['Contents'], key=lambda x: x['LastModified'], reverse=True)
        latest = images[0]
        
        filename = latest['Key'].split('/')[-1]
        download_path = f"./emergency_images/{filename}"
        
        # Create directory if it doesn't exist
        os.makedirs("./emergency_images", exist_ok=True)
        
        # Download the image
        print(f"\n📥 Downloading latest image: {filename}")
        s3.download_file(bucket_name, latest['Key'], download_path)
        
        print(f"✅ Image downloaded to: {download_path}")
        return download_path
        
    except Exception as e:
        print(f"❌ Error downloading image: {e}")
        return None

def show_image_stats():
    """Show statistics about emergency images"""
    try:
        bucket_name = os.getenv('AWS_S3_EMERGENCY_BUCKET')
        region = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        s3 = boto3.client('s3', region_name=region)
        
        total_size = 0
        count = 0
        newest_date = None
        oldest_date = None
        
        paginator = s3.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=bucket_name, Prefix='emergency-images/')
        
        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    count += 1
                    total_size += obj['Size']
                    
                    modified = obj['LastModified']
                    if newest_date is None or modified > newest_date:
                        newest_date = modified
                    if oldest_date is None or modified < oldest_date:
                        oldest_date = modified
        
        print("\n" + "="*70)
        print("📊 EMERGENCY IMAGES STATISTICS")
        print("="*70)
        
        if count > 0:
            print(f"Total Images: {count}")
            print(f"Total Size: {total_size:,} bytes ({total_size/1024/1024:.2f} MB)")
            print(f"Average Size: {total_size/count/1024:.2f} KB")
            if newest_date:
                print(f"Newest Image: {newest_date.strftime('%Y-%m-%d %H:%M:%S')}")
            if oldest_date:
                print(f"Oldest Image: {oldest_date.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            print("No emergency images found")
        
        print("="*70 + "\n")
        
    except Exception as e:
        print(f"❌ Error getting statistics: {e}")

def main():
    print("\n🔍 VIEWING EMERGENCY IMAGES")
    print("="*70)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Region: {os.getenv('AWS_DEFAULT_REGION', 'us-east-1')}")
    
    # Show statistics
    show_image_stats()
    
    # List all images
    count = list_emergency_images()
    
    # Offer to download latest if images exist
    if count > 0:
        print("\n" + "="*70)
        print("💡 TIP: You can view images using the presigned URLs above")
        print("        (URLs are valid for 1 hour)")
        print("="*70)
    
    print("\n✅ Image listing complete!\n")

if __name__ == "__main__":
    main()
