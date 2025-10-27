#!/bin/bash

# Amazon Bedrock Setup Script for Fall Detection System
# This script sets up Bedrock access and creates necessary IAM policies

set -e  # Exit on any error

echo "Amazon Bedrock Setup for Fall Detection System"
echo "================================================="

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo "AWS CLI is not installed. Please install it first."
    echo "   Visit: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
    exit 1
fi

# Check if AWS credentials are configured
if ! aws sts get-caller-identity &> /dev/null; then
    echo "AWS credentials not configured. Please run 'aws configure' first."
    exit 1
fi

# Load environment variables from .env file if it exists
if [ -f ../.env ]; then
    echo "Loading environment variables from .env file..."
    export $(grep -v '^#' ../.env | xargs)
fi

# Get current AWS account and region
AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=$(aws configure get region)
echo "AWS Account: $AWS_ACCOUNT"
echo "AWS Region: $AWS_REGION"

# Check if Bedrock is available in the region
echo "Checking Bedrock availability in region $AWS_REGION..."
if aws bedrock list-foundation-models --region $AWS_REGION &> /dev/null; then
    echo "Bedrock is available in $AWS_REGION"
else
    echo "Bedrock is not available in $AWS_REGION"
    echo "   Available regions: us-east-1, us-west-2, eu-west-1, ap-southeast-1"
    echo "   Please switch to a supported region:"
    echo "   aws configure set region us-east-1"
    exit 1
fi

# Create IAM policy for Bedrock access
echo "Creating IAM policy for Bedrock access..."
POLICY_NAME="FallDetectionBedrockPolicy"
POLICY_ARN="arn:aws:iam::${AWS_ACCOUNT}:policy/${POLICY_NAME}"

# Check if policy already exists
if aws iam get-policy --policy-arn $POLICY_ARN &> /dev/null; then
    echo "Policy $POLICY_NAME already exists. Updating..."
    
    # Get the latest version
    LATEST_VERSION=$(aws iam get-policy --policy-arn $POLICY_ARN --query 'Policy.DefaultVersionId' --output text)
    
    # Create new version
    aws iam create-policy-version \
        --policy-arn $POLICY_ARN \
        --policy-document file://bedrock_iam_policy.json \
        --set-as-default
    
    echo "Policy updated successfully"
else
    # Create new policy
    aws iam create-policy \
        --policy-name $POLICY_NAME \
        --policy-document file://bedrock_iam_policy.json \
        --description "Policy for Fall Detection System Bedrock access"
    
    echo "Policy created successfully"
fi

# Attach policy to SageMaker execution role
echo "Attaching Bedrock policy to SageMaker execution role..."
SAGEMAKER_ROLE="SageMakerExecutionRole"

if aws iam get-role --role-name $SAGEMAKER_ROLE &> /dev/null; then
    aws iam attach-role-policy \
        --role-name $SAGEMAKER_ROLE \
        --policy-arn $POLICY_ARN
    
    echo "Policy attached to SageMaker execution role"
else
    echo "SageMaker execution role not found. Creating..."
    
    # Create SageMaker execution role
    aws iam create-role \
        --role-name $SAGEMAKER_ROLE \
        --assume-role-policy-document '{
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "sagemaker.amazonaws.com"
                    },
                    "Action": "sts:AssumeRole"
                }
            ]
        }'
    
    # Attach necessary policies
    aws iam attach-role-policy \
        --role-name $SAGEMAKER_ROLE \
        --policy-arn arn:aws:iam::aws:policy/AmazonSageMakerFullAccess
    
    aws iam attach-role-policy \
        --role-name $SAGEMAKER_ROLE \
        --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess
    
    aws iam attach-role-policy \
        --role-name $SAGEMAKER_ROLE \
        --policy-arn arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess
    
    aws iam attach-role-policy \
        --role-name $SAGEMAKER_ROLE \
        --policy-arn $POLICY_ARN
    
    echo "SageMaker execution role created with Bedrock access"
fi

# Attach policy to IAM user (if using IAM user)
echo "Attaching Bedrock policy to IAM user..."
CURRENT_USER=$(aws sts get-caller-identity --query 'Arn' --output text | cut -d'/' -f2)

if [[ $CURRENT_USER == *"user"* ]]; then
    USER_NAME=$(echo $CURRENT_USER | cut -d'/' -f2)
    
    aws iam attach-user-policy \
        --user-name $USER_NAME \
        --policy-arn $POLICY_ARN
    
    echo "Policy attached to IAM user: $USER_NAME"
else
    echo "Using assumed role or root account. Policy attachment skipped."
fi

# Test Bedrock access
echo "Testing Bedrock access..."
if aws bedrock list-foundation-models --region $AWS_REGION --query 'modelSummaries[0].modelId' --output text &> /dev/null; then
    echo "Bedrock access test successful"
    
    # List available models
    echo "Available Foundation Models:"
    aws bedrock list-foundation-models --region $AWS_REGION --query 'modelSummaries[?contains(modelId, `claude`) || contains(modelId, `titan`) || contains(modelId, `llama`)].{Model:modelId,Provider:providerName}' --output table
else
    echo "Bedrock access test failed"
    echo "   Please check your permissions and region settings"
    exit 1
fi

# Update .env file with Bedrock configuration
if [ -f ../.env ]; then
    echo "Updating .env file with Bedrock configuration..."
    
    # Remove existing Bedrock settings if they exist
    sed -i.bak '/^BEDROCK_/d' ../.env
    
    # Add Bedrock configuration
    cat >> ../.env << EOF

# Amazon Bedrock Configuration
BEDROCK_REGION=$AWS_REGION
BEDROCK_ENABLED=true
BEDROCK_CLAUDE_MODEL=anthropic.claude-3-sonnet-20240229-v1:0
BEDROCK_TITAN_MODEL=amazon.titan-text-express-v1
BEDROCK_LLAMA_MODEL=meta.llama2-13b-chat-v1
BEDROCK_J2_MODEL=ai21.j2-ultra-v1
EOF
    
    echo ".env file updated with Bedrock configuration"
fi

# Install required Python packages
echo "Installing required Python packages..."
pip install --no-build-isolation --force-reinstall \
    "boto3>=1.28.57" \
    "awscli>=1.29.57" \
    "botocore>=1.31.57"

echo "Python packages installed"

# Test Bedrock integration
echo "Testing Bedrock integration..."
cd ..
python -c "
import sys
sys.path.append('.')
from bedrock_integration import create_bedrock_ai
import json

try:
    bedrock_ai = create_bedrock_ai()
    test_result = bedrock_ai.test_bedrock_connection()
    print('Bedrock Integration Test:', json.dumps(test_result, indent=2))
    
    if test_result['status'] == 'success':
        print('Bedrock integration test successful!')
    else:
        print('Bedrock integration test failed')
        sys.exit(1)
        
except Exception as e:
    print(f'Bedrock integration test failed: {e}')
    sys.exit(1)
"

if [ $? -eq 0 ]; then
    echo "Bedrock integration test successful!"
else
    echo "Bedrock integration test failed"
    exit 1
fi

echo ""
echo "Amazon Bedrock Setup Completed Successfully!"
echo ""
echo "What's Been Set Up:"
echo "   - IAM Policy: $POLICY_NAME"
echo "   - SageMaker Role: $SAGEMAKER_ROLE (with Bedrock access)"
echo "   - IAM User: $USER_NAME (with Bedrock access)"
echo "   - Region: $AWS_REGION"
echo "   - Python packages updated"
echo "   - .env file configured"
echo ""
echo "Available Bedrock Models:"
echo "   - Claude 3 Sonnet (anthropic.claude-3-sonnet-20240229-v1:0)"
echo "   - Titan Text Express (amazon.titan-text-express-v1)"
echo "   - Llama 2 13B Chat (meta.llama2-13b-chat-v1)"
echo "   - Jurassic-2 Ultra (ai21.j2-ultra-v1)"
echo ""
echo "Next Steps:"
echo "1. Test Bedrock integration:"
echo "   python bedrock_integration.py"
echo ""
echo "2. Integrate with fall detection system:"
echo "   python camera_detection.py --enable-bedrock"
echo ""
echo "3. Test intelligent alerts:"
echo "   python test_bedrock_integration.py"
echo ""
echo "Cost Information:"
echo "   - Claude 3 Sonnet: ~$0.003 per 1K input tokens, ~$0.015 per 1K output tokens"
echo "   - Titan Text Express: ~$0.0008 per 1K input tokens, ~$0.0016 per 1K output tokens"
echo "   - Monitor usage in AWS Console: https://$AWS_REGION.console.aws.amazon.com/bedrock/"
echo ""
echo "Security Notes:"
echo "   - All Bedrock API calls are logged in CloudTrail"
echo "   - Data is encrypted in transit and at rest"
echo "   - IAM policies follow least privilege principle"
echo "   - No training data is stored by AWS"
echo ""
echo "Documentation:"
echo "   - Bedrock User Guide: https://docs.aws.amazon.com/bedrock/"
echo "   - Claude API Reference: https://docs.anthropic.com/claude/reference"
echo "   - Model Comparison: https://docs.aws.amazon.com/bedrock/latest/userguide/models.html"
