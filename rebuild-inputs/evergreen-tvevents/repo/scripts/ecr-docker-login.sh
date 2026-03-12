#!/bin/bash

# Usage: ./setup-ecr-docker.sh <repo-name> <region>
# Example: ./setup-ecr-docker.sh my-app us-west-2

if [ $# -lt 2 ]; then
    echo "Usage: $0 <repo-name> <region>"
    echo "Example: $0 my-app us-west-2"
    exit 1
fi

REPO_NAME=$1
REGION=$2

# Get repository URI
ECR_URI=$(aws ecr describe-repositories --repository-names $REPO_NAME --region $REGION --query 'repositories[0].repositoryUri' --output text)

# Login to Docker
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ECR_URI

echo "Connected to repository: $ECR_URI"
echo "Docker logged in successfully"

# Verify repository exists
echo "Verifying repository..."
aws ecr describe-repositories --repository-names $REPO_NAME --region $REGION --query 'repositories[0].[repositoryName,createdAt]' --output table