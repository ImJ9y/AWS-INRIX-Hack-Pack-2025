#!/usr/bin/env python3
"""
AWS Infrastructure Setup Script for Fall Detection Emergency System
This script deploys the CloudFormation template and sets up AWS resources.
"""

import argparse
import json
import sys
import time
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError, WaiterError


class AWSInfrastructureSetup:
    """Class to handle AWS infrastructure setup"""

    def __init__(self, region: str = "us-east-1"):
        self.region = region
        self.cloudformation = boto3.client("cloudformation", region_name=region)
        self.iot = boto3.client("iot", region_name=region)
        self.sns = boto3.client("sns", region_name=region)

    def deploy_cloudformation_stack(
        self, stack_name: str, template_file: str, parameters: Dict[str, str]
    ) -> bool:
        """Deploy CloudFormation stack"""
        try:
            # Read CloudFormation template
            with open(template_file, "r") as f:
                template_body = f.read()

            # Check if stack exists
            try:
                self.cloudformation.describe_stacks(StackName=stack_name)
                stack_exists = True
                print(f"Stack {stack_name} already exists. Updating...")
            except ClientError as e:
                if e.response["Error"]["Code"] == "ValidationError":
                    stack_exists = False
                    print(f"Stack {stack_name} does not exist. Creating...")
                else:
                    raise e

            # Prepare parameters
            cf_parameters = []
            for key, value in parameters.items():
                cf_parameters.append({"ParameterKey": key, "ParameterValue": value})

            if stack_exists:
                # Update existing stack
                response = self.cloudformation.update_stack(
                    StackName=stack_name,
                    TemplateBody=template_body,
                    Parameters=cf_parameters,
                    Capabilities=["CAPABILITY_NAMED_IAM"],
                )
                operation = "UPDATE"
            else:
                # Create new stack
                response = self.cloudformation.create_stack(
                    StackName=stack_name,
                    TemplateBody=template_body,
                    Parameters=cf_parameters,
                    Capabilities=["CAPABILITY_NAMED_IAM"],
                )
                operation = "CREATE"

            print(f"CloudFormation {operation} initiated: {response['StackId']}")

            # Wait for stack operation to complete
            waiter = self.cloudformation.get_waiter(
                f"stack_{operation.lower()}_complete"
            )
            print(f"Waiting for stack {operation.lower()} to complete...")
            waiter.wait(StackName=stack_name)

            print(f"Stack {operation.lower()} completed successfully!")
            return True

        except WaiterError as e:
            print(f"Stack operation failed: {e}")
            return False
        except ClientError as e:
            print(f"AWS error: {e}")
            return False
        except Exception as e:  # pylint: disable=broad-exception-caught
            print(f"Unexpected error: {e}")
            return False

    def get_stack_outputs(self, stack_name: str) -> Dict[str, str]:
        """Get CloudFormation stack outputs"""
        try:
            response = self.cloudformation.describe_stacks(StackName=stack_name)
            stack = response["Stacks"][0]
            outputs = {}
            for output in stack.get("Outputs", []):
                outputs[output["OutputKey"]] = output["OutputValue"]
            return outputs
        except ClientError as e:
            print(f"Error getting stack outputs: {e}")
            return {}

    def create_iot_thing(self, thing_name: str) -> bool:
        """Create IoT thing"""
        try:
            self.iot.create_thing(thingName=thing_name)
            print(f"IoT thing '{thing_name}' created successfully")
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceAlreadyExistsException":
                print(f"IoT thing '{thing_name}' already exists")
                return True
            else:
                print(f"Error creating IoT thing: {e}")
                return False

    def create_iot_certificate(self, thing_name: str) -> Dict[str, str]:
        """Create IoT certificate and keys"""
        try:
            # Create certificate
            response = self.iot.create_keys_and_certificate(setAsActive=True)
            certificate_arn = response["certificateArn"]
            certificate_id = response["certificateId"]

            # Save certificate and keys to files
            cert_dir = "certs"
            import os

            os.makedirs(cert_dir, exist_ok=True)

            # Save certificate
            cert_file = f"{cert_dir}/device-certificate.pem.crt"
            with open(cert_file, "w") as f:
                f.write(response["certificatePem"])

            # Save private key
            key_file = f"{cert_dir}/private.pem.key"
            with open(key_file, "w") as f:
                f.write(response["keyPair"]["PrivateKey"])

            # Save public key
            pub_key_file = f"{cert_dir}/public.pem.key"
            with open(pub_key_file, "w") as f:
                f.write(response["keyPair"]["PublicKey"])

            print(f"Certificate and keys saved to {cert_dir}/")

            return {
                "certificate_arn": certificate_arn,
                "certificate_id": certificate_id,
                "certificate_file": cert_file,
                "private_key_file": key_file,
                "public_key_file": pub_key_file,
            }

        except ClientError as e:
            print(f"Error creating IoT certificate: {e}")
            return {}

    def attach_iot_policy(self, certificate_arn: str, policy_name: str) -> bool:
        """Attach IoT policy to certificate"""
        try:
            self.iot.attach_policy(policyName=policy_name, target=certificate_arn)
            print(f"IoT policy '{policy_name}' attached to certificate")
            return True
        except ClientError as e:
            print(f"Error attaching IoT policy: {e}")
            return False

    def attach_thing_principal(self, thing_name: str, certificate_arn: str) -> bool:
        """Attach certificate to IoT thing"""
        try:
            self.iot.attach_thing_principal(
                thingName=thing_name, principal=certificate_arn
            )
            print(f"Certificate attached to IoT thing '{thing_name}'")
            return True
        except ClientError as e:
            print(f"Error attaching certificate to thing: {e}")
            return False

    def download_root_ca(self) -> str:
        """Download AWS IoT Root CA certificate"""
        try:
            import ssl
            import urllib.request

            cert_dir = "certs"
            import os

            os.makedirs(cert_dir, exist_ok=True)

            ca_file = f"{cert_dir}/AmazonRootCA1.pem"

            # Download Root CA certificate
            url = "https://www.amazontrust.com/repository/AmazonRootCA1.pem"
            urllib.request.urlretrieve(url, ca_file)

            print(f"Root CA certificate downloaded to {ca_file}")
            return ca_file

        except Exception as e:
            print(f"Error downloading Root CA certificate: {e}")
            return ""

    def get_iot_endpoint(self) -> str:
        """Get AWS IoT endpoint"""
        try:
            response = self.iot.describe_endpoint(endpointType="iot:Data-ATS")
            return response["endpointAddress"]
        except ClientError as e:
            print(f"Error getting IoT endpoint: {e}")
            return ""

    def setup_sns_subscriptions(self, topic_arns: Dict[str, str]) -> bool:
        """Set up SNS topic subscriptions"""
        try:
            print("Setting up SNS subscriptions...")
            print(
                "Note: You'll need to manually configure email and SMS subscriptions in the AWS Console"
            )
            print("Topic ARNs:")
            for name, arn in topic_arns.items():
                print(f" {name}: {arn}")
            return True
        except Exception as e:
            print(f"Error setting up SNS subscriptions: {e}")
            return False

    def update_config_file(
        self,
        stack_outputs: Dict[str, str],
        certificate_info: Dict[str, str],
        iot_endpoint: str,
    ) -> bool:
        """Update config.json and .env file with AWS resource information"""
        try:
            # Update config.json
            config_file = "../config.json"
            try:
                with open(config_file, "r") as f:
                    config = json.load(f)
            except FileNotFoundError:
                config = {}

            # Update AWS services configuration
            if "aws_services" not in config:
                config["aws_services"] = {}

            aws_config = config["aws_services"]
            aws_config["region"] = self.region

            # Initialize nested dictionaries if they don't exist
            if "iot_core" not in aws_config:
                aws_config["iot_core"] = {}
            if "sns" not in aws_config:
                aws_config["sns"] = {}
            if "s3" not in aws_config:
                aws_config["s3"] = {}
            if "dynamodb" not in aws_config:
                aws_config["dynamodb"] = {}
            if "lambda" not in aws_config:
                aws_config["lambda"] = {}
            if "cloudwatch" not in aws_config:
                aws_config["cloudwatch"] = {}

            aws_config["iot_core"]["endpoint"] = iot_endpoint
            aws_config["iot_core"]["certificate_path"] = certificate_info.get(
                "certificate_file", ""
            )
            aws_config["iot_core"]["private_key_path"] = certificate_info.get(
                "private_key_file", ""
            )
            aws_config["iot_core"]["root_ca_path"] = "certs/AmazonRootCA1.pem"

            # Update SNS topic ARNs
            aws_config["sns"]["emergency_topic_arn"] = stack_outputs.get(
                "EmergencyTopicArn", ""
            )
            aws_config["sns"]["notification_topic_arn"] = stack_outputs.get(
                "NotificationTopicArn", ""
            )

            # Update S3 bucket name
            aws_config["s3"]["bucket_name"] = stack_outputs.get(
                "EmergencyDataBucketName", ""
            )

            # Update DynamoDB table names
            aws_config["dynamodb"]["table_name"] = stack_outputs.get(
                "EventsTableName", ""
            )
            aws_config["dynamodb"]["analytics_table_name"] = stack_outputs.get(
                "AnalyticsTableName", ""
            )

            # Update Lambda function names
            aws_config["lambda"]["emergency_processor_function"] = stack_outputs.get(
                "EmergencyProcessorFunctionName", ""
            )
            aws_config["lambda"]["analytics_function"] = stack_outputs.get(
                "AnalyticsProcessorFunctionName", ""
            )

            # Update CloudWatch log group
            aws_config["cloudwatch"]["log_group"] = stack_outputs.get(
                "CloudWatchLogGroupName", ""
            )

            config["aws_services"] = aws_config

            # Write updated config
            with open(config_file, "w") as f:
                json.dump(config, f, indent=2)

            print(f"Configuration updated in {config_file}")

            # Update .env file
            env_file = "../.env"
            env_updates = {
                "AWS_DEFAULT_REGION": self.region,
                "AWS_IOT_ENDPOINT": iot_endpoint,
                "AWS_IOT_CERT_PATH": certificate_info.get("certificate_file", ""),
                "AWS_IOT_PRIVATE_KEY_PATH": certificate_info.get(
                    "private_key_file", ""
                ),
                "AWS_IOT_ROOT_CA_PATH": "certs/AmazonRootCA1.pem",
                "AWS_SNS_EMERGENCY_TOPIC_ARN": stack_outputs.get(
                    "EmergencyTopicArn", ""
                ),
                "AWS_SNS_NOTIFICATION_TOPIC_ARN": stack_outputs.get(
                    "NotificationTopicArn", ""
                ),
                "AWS_S3_BUCKET_NAME": stack_outputs.get("EmergencyDataBucketName", ""),
                "AWS_DYNAMODB_EVENTS_TABLE": stack_outputs.get("EventsTableName", ""),
                "AWS_DYNAMODB_ANALYTICS_TABLE": stack_outputs.get(
                    "AnalyticsTableName", ""
                ),
                "AWS_LAMBDA_EMERGENCY_PROCESSOR": stack_outputs.get(
                    "EmergencyProcessorFunctionName", ""
                ),
                "AWS_LAMBDA_ANALYTICS_PROCESSOR": stack_outputs.get(
                    "AnalyticsProcessorFunctionName", ""
                ),
                "AWS_CLOUDWATCH_LOG_GROUP": stack_outputs.get(
                    "CloudWatchLogGroupName", ""
                ),
            }

            # Read existing .env file
            env_lines = []
            try:
                with open(env_file, "r") as f:
                    env_lines = f.readlines()
            except FileNotFoundError:
                print(f"Creating new .env file: {env_file}")

            # Update or add environment variables
            updated_vars = set()
            for i, line in enumerate(env_lines):
                if "=" in line and not line.strip().startswith("#"):
                    key = line.split("=")[0].strip()
                    if key in env_updates:
                        env_lines[i] = f"{key}={env_updates[key]}\n"
                        updated_vars.add(key)

            # Add new variables that weren't in the file
            for key, value in env_updates.items():
                if key not in updated_vars:
                    env_lines.append(f"{key}={value}\n")

            # Write updated .env file
            with open(env_file, "w") as f:
                f.writelines(env_lines)

            print(f"Environment variables updated in {env_file}")
            return True

        except Exception as e:
            print(f"Error updating config files: {e}")
            return False


def main():
    parser = argparse.ArgumentParser(
        description="Setup AWS infrastructure for Fall Detection System"
    )
    parser.add_argument("--region", default="us-east-1", help="AWS region")
    parser.add_argument(
        "--environment",
        default="dev",
        choices=["dev", "staging", "prod"],
        help="Environment name",
    )
    parser.add_argument("--project-name", default="fall-detection", help="Project name")
    parser.add_argument(
        "--thing-name", default="fall-detection-camera", help="IoT thing name"
    )
    parser.add_argument(
        "--skip-cloudformation",
        action="store_true",
        help="Skip CloudFormation deployment",
    )
    parser.add_argument("--skip-iot", action="store_true", help="Skip IoT setup")

    args = parser.parse_args()

    setup = AWSInfrastructureSetup(args.region)

    print(
        f"Setting up AWS infrastructure for {args.project_name} in {args.environment} environment"
    )
    print(f"Region: {args.region}")
    print("=" * 60)

    # Deploy CloudFormation stack
    if not args.skip_cloudformation:
        stack_name = f"{args.project_name}-infrastructure-{args.environment}"
        template_file = "cloudformation_template.yaml"

        parameters = {"Environment": args.environment, "ProjectName": args.project_name}

        print("Deploying CloudFormation stack...")
        if not setup.deploy_cloudformation_stack(stack_name, template_file, parameters):
            print("CloudFormation deployment failed!")
            sys.exit(1)

        # Get stack outputs
        stack_outputs = setup.get_stack_outputs(stack_name)
        print("Stack outputs retrieved successfully")
    else:
        print("Skipping CloudFormation deployment")
        stack_outputs = {}

    # Setup IoT Core
    if not args.skip_iot:
        print("\nSetting up IoT Core...")

        # Create IoT thing
        if not setup.create_iot_thing(args.thing_name):
            print("Failed to create IoT thing")
            sys.exit(1)

        # Create certificate and keys
        certificate_info = setup.create_iot_certificate(args.thing_name)
        if not certificate_info:
            print("Failed to create IoT certificate")
            sys.exit(1)

        # Attach policy to certificate
        policy_name = f"{args.project_name}-iot-policy-{args.environment}"
        if not setup.attach_iot_policy(
            certificate_info["certificate_arn"], policy_name
        ):
            print("Failed to attach IoT policy")
            sys.exit(1)

        # Attach certificate to thing
        if not setup.attach_thing_principal(
            args.thing_name, certificate_info["certificate_arn"]
        ):
            print("Failed to attach certificate to thing")
            sys.exit(1)

        # Download Root CA certificate
        ca_file = setup.download_root_ca()
        if not ca_file:
            print("Failed to download Root CA certificate")
            sys.exit(1)

        # Get IoT endpoint
        iot_endpoint = setup.get_iot_endpoint()
        if not iot_endpoint:
            print("Failed to get IoT endpoint")
            sys.exit(1)

        print(f"IoT endpoint: {iot_endpoint}")
    else:
        print("Skipping IoT setup")
        certificate_info = {}
        iot_endpoint = ""

    # Setup SNS subscriptions
    if stack_outputs:
        topic_arns = {
            "Emergency": stack_outputs.get("EmergencyTopicArn", ""),
            "Notification": stack_outputs.get("NotificationTopicArn", ""),
            "Critical": stack_outputs.get("CriticalTopicArn", ""),
        }
        setup.setup_sns_subscriptions(topic_arns)

    # Update configuration file
    if stack_outputs and certificate_info and iot_endpoint:
        print("\nUpdating configuration file...")
        if setup.update_config_file(stack_outputs, certificate_info, iot_endpoint):
            print("Configuration updated successfully!")
        else:
            print("Failed to update configuration file")

    print("\n" + "=" * 60)
    print("AWS infrastructure setup completed!")
    print("\nNext steps:")
    print("1. Configure SNS email and SMS subscriptions in AWS Console")
    print("2. Deploy Lambda function code (upload the lambda_functions/ directory)")
    print("3. Test the system with: python camera_detection.py")
    print("4. Monitor logs in CloudWatch")
    print("\nImportant files created:")
    print("- certs/device-certificate.pem.crt")
    print("- certs/private.pem.key")
    print("- certs/AmazonRootCA1.pem")
    print("- Updated config.json")


if __name__ == "__main__":
    main()
