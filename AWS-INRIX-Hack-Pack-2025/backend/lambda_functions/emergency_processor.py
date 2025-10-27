#!/usr/bin/env python3
"""
AWS Lambda function for processing emergency events from the Fall Detection System
This function processes emergency events, triggers additional notifications, and updates databases.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict

import boto3

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
sns_client = boto3.client("sns")
dynamodb = boto3.resource("dynamodb")
cloudwatch = boto3.client("cloudwatch")


def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Lambda handler for processing emergency events

    Args:
    event: Event data from the fall detection system
    context: Lambda context object

    Returns:
    Response dictionary with status and message
    """
    try:
        logger.info(f"Processing emergency event: {json.dumps(event)}")

        # Extract event data
        event_id = event.get("event_id", "unknown")
        camera_id = event.get("camera_id", "unknown")
        zone = event.get("zone", "unknown")
        severity = event.get("severity", 0)
        person_id = event.get("person_id", 0)
        timestamp = event.get("timestamp", datetime.now(timezone.utc).isoformat())

        # Process emergency event
        result = process_emergency_event(event)

        # Send additional notifications if needed
        if severity >= 9:  # Critical emergency
            send_critical_alert(event)

        # Update emergency response tracking
        update_emergency_tracking(event)

        # Publish metrics
        publish_emergency_metrics(event)

        logger.info(f"Emergency event {event_id} processed successfully")

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "message": "Emergency event processed successfully",
                    "event_id": event_id,
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                }
            ),
        }

    except Exception as e:
        logger.error(f"Error processing emergency event: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps(
                {"error": "Failed to process emergency event", "message": str(e)}
            ),
        }


def process_emergency_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Process the emergency event and perform necessary actions"""

    # Log the emergency event
    logger.info(
        f"EMERGENCY PROCESSING: {
            event.get(
                'description',
                'No description')}"
    )

    # Add processing timestamp
    event["processed_at"] = datetime.now(timezone.utc).isoformat()
    event["processing_status"] = "processed"

    # Determine response level based on severity
    severity = event.get("severity", 0)
    if severity >= 9:
        event["response_level"] = "critical"
        event["escalation_required"] = True
    elif severity >= 8:
        event["response_level"] = "emergency"
        event["escalation_required"] = False
    else:
        event["response_level"] = "monitoring"
        event["escalation_required"] = False

    return event


def send_critical_alert(event: Dict[str, Any]) -> bool:
    """Send critical alert for high-severity emergencies"""
    try:
        # Get critical alert topic ARN from environment or config
        critical_topic_arn = os.getenv(
            "AWS_SNS_CRITICAL_TOPIC_ARN",
            "arn:aws:sns:us-east-1:123456789012:fall-detection-critical",
        )

        message = {
            "default": json.dumps(event),
            "email": format_critical_email(event),
            "sms": format_critical_sms(event),
        }

        response = sns_client.publish(
            TopicArn=critical_topic_arn,
            Message=json.dumps(message),
            Subject=f"CRITICAL ALERT - Fall Detection - {event.get('camera_id', 'Unknown')}",
            MessageStructure="json",
        )

        logger.info(f"Critical alert sent: {response['MessageId']}")
        return True

    except Exception as e:
        logger.error(f"Failed to send critical alert: {e}")
        return False


def update_emergency_tracking(event: Dict[str, Any]) -> bool:
    """Update emergency tracking in DynamoDB"""
    try:
        table_name = os.getenv(
            "AWS_DYNAMODB_TRACKING_TABLE", "FallDetectionEmergencyTracking"
        )
        table = dynamodb.Table(table_name)

        tracking_item = {
            "event_id": event.get("event_id", "unknown"),
            "camera_id": event.get("camera_id", "unknown"),
            "zone": event.get("zone", "unknown"),
            "severity": event.get("severity", 0),
            "person_id": event.get("person_id", 0),
            "timestamp": event.get("timestamp", datetime.now(timezone.utc).isoformat()),
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "response_level": event.get("response_level", "monitoring"),
            "escalation_required": event.get("escalation_required", False),
            "status": "active",
            # 7 days TTL
            "ttl": int(datetime.now(timezone.utc).timestamp()) + (7 * 24 * 60 * 60),
        }

        table.put_item(Item=tracking_item)
        logger.info(f"Emergency tracking updated for event {event.get('event_id')}")
        return True

    except Exception as e:
        logger.error(f"Failed to update emergency tracking: {e}")
        return False


def publish_emergency_metrics(event: Dict[str, Any]) -> bool:
    """Publish emergency metrics to CloudWatch"""
    try:
        metrics = [
            {
                "MetricName": "EmergencyEvents",
                "Value": 1,
                "Unit": "Count",
                "Timestamp": datetime.now(timezone.utc),
                "Dimensions": [
                    {"Name": "CameraId", "Value": event.get("camera_id", "unknown")},
                    {"Name": "Zone", "Value": event.get("zone", "unknown")},
                    {"Name": "SeverityLevel", "Value": str(event.get("severity", 0))},
                ],
            },
            {
                "MetricName": "EmergencySeverity",
                "Value": event.get("severity", 0),
                "Unit": "None",
                "Timestamp": datetime.now(timezone.utc),
                "Dimensions": [
                    {"Name": "CameraId", "Value": event.get("camera_id", "unknown")},
                    {"Name": "Zone", "Value": event.get("zone", "unknown")},
                ],
            },
        ]

        namespace = os.getenv(
            "AWS_CLOUDWATCH_METRICS_NAMESPACE", "FallDetection/Emergency"
        )
        cloudwatch.put_metric_data(Namespace=namespace, MetricData=metrics)

        logger.info("Emergency metrics published to CloudWatch")
        return True

    except Exception as e:
        logger.error(f"Failed to publish emergency metrics: {e}")
        return False


def format_critical_email(event: Dict[str, Any]) -> str:
    """Format critical alert email message"""
    return f"""
CRITICAL EMERGENCY ALERT - Fall Detection System

URGENT: High-severity fall detected requiring immediate attention!

Event Details:
- Event ID: {event.get('event_id', 'Unknown')}
- Timestamp: {event.get('timestamp', 'Unknown')}
- Camera ID: {event.get('camera_id', 'Unknown')}
- Zone: {event.get('zone', 'Unknown')}
- Severity Level: {event.get('severity', 0)}/10
- Person ID: {event.get('person_id', 'Unknown')}
- Location: {event.get('location', 'Unknown')}
- Description: {event.get('description', 'No description available')}

This is a CRITICAL emergency requiring immediate response.
Please contact emergency services immediately if this is a genuine emergency.

System Status: CRITICAL EMERGENCY - IMMEDIATE ACTION REQUIRED
 """


def format_critical_sms(event: Dict[str, Any]) -> str:
    """Format critical alert SMS message"""
    return f"CRITICAL: Fall detected at {
        event.get(
            'camera_id',
            'Unknown')} - Severity {
        event.get(
            'severity',
            0)}/10 - IMMEDIATE ACTION REQUIRED"
