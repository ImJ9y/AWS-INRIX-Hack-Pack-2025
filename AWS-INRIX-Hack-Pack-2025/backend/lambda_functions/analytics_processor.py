#!/usr/bin/env python3
"""
AWS Lambda function for processing analytics data from the Fall Detection System
This function processes analytics data, generates insights, and updates reporting tables.
"""

import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import boto3

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource("dynamodb")
cloudwatch = boto3.client("cloudwatch")
s3_client = boto3.client("s3")


def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Lambda handler for processing analytics data

    Args:
        event: Analytics data from the fall detection system
        context: Lambda context object

    Returns:
        Response dictionary with status and message
    """
    try:
        logger.info(f"Processing analytics data: {json.dumps(event)}")

        # Extract analytics data
        camera_id = event.get("camera_id", "unknown")
        zone = event.get("zone", "unknown")
        timestamp = event.get("timestamp", datetime.now(timezone.utc).isoformat())

        # Process analytics data
        result = process_analytics_data(event)

        # Generate insights
        insights = generate_insights(event)

        # Update reporting tables
        update_reporting_tables(event, insights)

        # Publish analytics metrics
        publish_analytics_metrics(event, insights)

        logger.info(f"Analytics data for {camera_id} processed successfully")

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "message": "Analytics data processed successfully",
                    "camera_id": camera_id,
                    "zone": zone,
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                    "insights": insights,
                }
            ),
        }

    except Exception as e:
        logger.error(f"Error processing analytics data: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps(
                {"error": "Failed to process analytics data", "message": str(e)}
            ),
        }


def process_analytics_data(event: Dict[str, Any]) -> Dict[str, Any]:
    """Process the analytics data and calculate derived metrics"""
    try:
        # Extract basic metrics
        total_detections = event.get("total_detections", 0)
        fall_count = event.get("fall_count", 0)
        emergency_count = event.get("emergency_count", 0)
        max_severity = event.get("max_severity", 0)
        avg_severity = event.get("avg_severity", 0.0)

        # Calculate rates
        fall_rate = (
            (fall_count / total_detections * 100) if total_detections > 0 else 0.0
        )
        emergency_rate = (
            (emergency_count / total_detections * 100) if total_detections > 0 else 0.0
        )

        # Determine risk level
        risk_level = "low"
        if max_severity >= 8 or emergency_count > 0:
            risk_level = "high"
        elif max_severity >= 6 or fall_rate > 10:
            risk_level = "medium"

        return {
            "total_detections": total_detections,
            "fall_count": fall_count,
            "emergency_count": emergency_count,
            "max_severity": max_severity,
            "avg_severity": avg_severity,
            "fall_rate": fall_rate,
            "emergency_rate": emergency_rate,
            "risk_level": risk_level,
        }

    except Exception as e:
        logger.error(f"Error processing analytics data: {e}")
        return {}


def generate_insights(event: Dict[str, Any]) -> Dict[str, Any]:
    """Generate insights and recommendations from analytics data"""
    try:
        # Calculate derived metrics
        total_detections = event.get("total_detections", 0)
        fall_count = event.get("fall_count", 0)
        emergency_count = event.get("emergency_count", 0)
        max_severity = event.get("max_severity", 0)
        avg_severity = event.get("avg_severity", 0.0)

        # Calculate rates
        fall_rate = (
            (fall_count / total_detections * 100) if total_detections > 0 else 0.0
        )
        emergency_rate = (
            (emergency_count / total_detections * 100) if total_detections > 0 else 0.0
        )

        # Generate insights
        insights = {
            "total_activity": total_detections,
            "fall_incidents": fall_count,
            "emergency_incidents": emergency_count,
            "max_severity_level": max_severity,
            "avg_severity_level": avg_severity,
            "fall_frequency": fall_rate,
            "assessment_timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Generate recommendations based on data
        recommendations = []

        if max_severity >= 8:
            recommendations.append(
                "High severity events detected - consider immediate safety review"
            )

        if fall_rate > 10:
            recommendations.append(
                "High fall rate detected - review environmental factors"
            )

        if event.get("emergency_count", 0) > 0:
            recommendations.append(
                "Emergency events detected - verify emergency response procedures"
            )

        if max_severity >= 6 and fall_rate > 5:
            recommendations.append(
                "Elevated risk detected - consider additional monitoring"
            )

        insights["recommendations"] = recommendations

        return insights

    except Exception as e:
        logger.error(f"Error generating insights: {e}")
        return {}


def update_reporting_tables(event: Dict[str, Any], insights: Dict[str, Any]) -> bool:
    """Update reporting tables with processed analytics data"""
    try:
        # Update daily analytics table
        daily_table_name = os.getenv(
            "AWS_DYNAMODB_DAILY_ANALYTICS_TABLE", "FallDetectionDailyAnalytics"
        )
        daily_table = dynamodb.Table(daily_table_name)

        date_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        hour_key = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H")

        daily_item = {
            "date_hour": hour_key,
            "date": date_key,
            "camera_id": event.get("camera_id", "unknown"),
            "zone": event.get("zone", "unknown"),
            "total_detections": event.get("total_detections", 0),
            "fall_count": event.get("fall_count", 0),
            "emergency_count": event.get("emergency_count", 0),
            "max_severity": event.get("max_severity", 0),
            "avg_severity": event.get("avg_severity", 0.0),
            "fall_rate": event.get("fall_rate", 0.0),
            "emergency_rate": event.get("emergency_rate", 0.0),
            "risk_level": event.get("risk_level", "low"),
            "insights": insights,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            # 1 year TTL
            "ttl": int(datetime.now(timezone.utc).timestamp()) + (365 * 24 * 60 * 60),
        }

        daily_table.put_item(Item=daily_item)

        # Update insights table
        insights_table_name = os.getenv(
            "AWS_DYNAMODB_INSIGHTS_TABLE", "FallDetectionInsights"
        )
        insights_table = dynamodb.Table(insights_table_name)

        insights_item = {
            "insight_id": f"{event.get('camera_id', 'unknown')}_{int(datetime.now(timezone.utc).timestamp())}",
            "camera_id": event.get("camera_id", "unknown"),
            "zone": event.get("zone", "unknown"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "insights": insights,
            "risk_level": event.get("risk_level", "low"),
            # 90 days TTL
            "ttl": int(datetime.now(timezone.utc).timestamp()) + (90 * 24 * 60 * 60),
        }

        insights_table.put_item(Item=insights_item)

        logger.info("Reporting tables updated successfully")
        return True

    except Exception as e:
        logger.error(f"Failed to update reporting tables: {e}")
        return False


def publish_analytics_metrics(event: Dict[str, Any], insights: Dict[str, Any]) -> bool:
    """Publish analytics metrics to CloudWatch"""
    try:
        metrics = [
            {
                "MetricName": "TotalDetections",
                "Value": event.get("total_detections", 0),
                "Unit": "Count",
                "Timestamp": datetime.now(timezone.utc),
                "Dimensions": [
                    {"Name": "CameraId", "Value": event.get("camera_id", "unknown")},
                    {"Name": "Zone", "Value": event.get("zone", "unknown")},
                ],
            },
            {
                "MetricName": "FallRate",
                "Value": event.get("fall_rate", 0.0),
                "Unit": "Percent",
                "Timestamp": datetime.now(timezone.utc),
                "Dimensions": [
                    {"Name": "CameraId", "Value": event.get("camera_id", "unknown")},
                    {"Name": "Zone", "Value": event.get("zone", "unknown")},
                ],
            },
            {
                "MetricName": "MaxSeverity",
                "Value": event.get("max_severity", 0),
                "Unit": "None",
                "Timestamp": datetime.now(timezone.utc),
                "Dimensions": [
                    {"Name": "CameraId", "Value": event.get("camera_id", "unknown")},
                    {"Name": "Zone", "Value": event.get("zone", "unknown")},
                ],
            },
        ]

        namespace = os.getenv(
            "AWS_CLOUDWATCH_METRICS_NAMESPACE", "FallDetection/Analytics"
        )
        cloudwatch.put_metric_data(Namespace=namespace, MetricData=metrics)

        logger.info("Analytics metrics published to CloudWatch successfully")
        return True

    except Exception as e:
        logger.error(f"Failed to publish analytics metrics: {e}")
        return False


def _generate_recommendations(event: Dict[str, Any]) -> List[str]:
    """Generate specific recommendations based on analytics data"""
    recommendations = []

    max_severity = event.get("max_severity", 0)
    fall_count = event.get("fall_count", 0)
    emergency_count = event.get("emergency_count", 0)
    total_detections = event.get("total_detections", 0)

    fall_rate = (fall_count / total_detections * 100) if total_detections > 0 else 0.0

    if max_severity >= 8:
        recommendations.append(
            "Critical severity events detected - immediate safety review required"
        )

    if emergency_count > 0:
        recommendations.append(
            "Emergency events detected - verify emergency response procedures"
        )

    if fall_rate > 15:
        recommendations.append(
            "High fall frequency - review environmental safety factors"
        )
    elif fall_rate > 5:
        recommendations.append(
            "Moderate fall frequency - consider additional monitoring"
        )

    if max_severity >= 6 and fall_rate > 5:
        recommendations.append("Elevated risk pattern - implement preventive measures")

    return recommendations


def _update_daily_analytics_table(
    event: Dict[str, Any], insights: Dict[str, Any]
) -> bool:
    """Update the daily analytics DynamoDB table"""
    try:
        table_name = os.getenv(
            "AWS_DYNAMODB_DAILY_ANALYTICS_TABLE", "FallDetectionDailyAnalytics"
        )
        table = dynamodb.Table(table_name)

        date_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        hour_key = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H")

        item = {
            "date_hour": hour_key,
            "date": date_key,
            "camera_id": event.get("camera_id", "unknown"),
            "zone": event.get("zone", "unknown"),
            "total_detections": event.get("total_detections", 0),
            "fall_count": event.get("fall_count", 0),
            "emergency_count": event.get("emergency_count", 0),
            "max_severity": event.get("max_severity", 0),
            "avg_severity": event.get("avg_severity", 0.0),
            "fall_rate": event.get("fall_rate", 0.0),
            "emergency_rate": event.get("emergency_rate", 0.0),
            "risk_level": event.get("risk_level", "low"),
            "insights": insights,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ttl": int(datetime.now(timezone.utc).timestamp()) + (365 * 24 * 60 * 60),
        }

        table.put_item(Item=item)
        return True

    except Exception as e:
        logger.error(f"Failed to update daily analytics table: {e}")
        return False


def _update_insights_table(event: Dict[str, Any], insights: Dict[str, Any]) -> bool:
    """Update the insights DynamoDB table"""
    try:
        table_name = os.getenv("AWS_DYNAMODB_INSIGHTS_TABLE", "FallDetectionInsights")
        table = dynamodb.Table(table_name)

        insight_id = f"{event.get('camera_id', 'unknown')}_{int(datetime.now(timezone.utc).timestamp())}"

        item = {
            "insight_id": insight_id,
            "camera_id": event.get("camera_id", "unknown"),
            "zone": event.get("zone", "unknown"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "insights": insights,
            "risk_level": event.get("risk_level", "low"),
            "ttl": int(datetime.now(timezone.utc).timestamp()) + (90 * 24 * 60 * 60),
        }

        table.put_item(Item=item)
        return True

    except Exception as e:
        logger.error(f"Failed to update insights table: {e}")
        return False


def _prepare_cloudwatch_metrics(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Prepare CloudWatch metrics for publishing"""
    metrics = []
    timestamp = datetime.now(timezone.utc)

    # Base dimensions
    dimensions = [
        {"Name": "CameraId", "Value": event.get("camera_id", "unknown")},
        {"Name": "Zone", "Value": event.get("zone", "unknown")},
    ]

    # Total detections metric
    metrics.append(
        {
            "MetricName": "TotalDetections",
            "Value": event.get("total_detections", 0),
            "Unit": "Count",
            "Timestamp": timestamp,
            "Dimensions": dimensions,
        }
    )

    # Fall rate metric
    metrics.append(
        {
            "MetricName": "FallRate",
            "Value": event.get("fall_rate", 0.0),
            "Unit": "Percent",
            "Timestamp": timestamp,
            "Dimensions": dimensions,
        }
    )

    # Max severity metric
    metrics.append(
        {
            "MetricName": "MaxSeverity",
            "Value": event.get("max_severity", 0),
            "Unit": "None",
            "Timestamp": timestamp,
            "Dimensions": dimensions,
        }
    )

    return metrics
