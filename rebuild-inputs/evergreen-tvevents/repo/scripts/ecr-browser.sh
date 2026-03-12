#!/bin/bash

# Usage: ./ecr-browser.sh <repo-name> <region>
# Example: ./ecr-browser.sh my-app us-west-2

if [ $# -lt 2 ]; then
    echo "Usage: $0 <repo-name> <region>"
    exit 1
fi

REPO_NAME=$1
REGION=$2

# Check if dialog is installed
if ! command -v dialog &> /dev/null; then
    echo "dialog is not installed. Please install it with:"
    echo "brew install dialog"
    exit 1
fi

# Get ECR URI
ECR_URI=$(aws ecr describe-repositories --repository-names $REPO_NAME --region $REGION --query 'repositories[0].repositoryUri' --output text)

# Get image tags
TAGS=$(aws ecr describe-images --repository-name $REPO_NAME --region $REGION --query 'reverse(sort_by(imageDetails, &imagePushedAt))[*].imageTags[0]' --output text | tr '\t' '\n' | grep -v None)

if [ -z "$TAGS" ]; then
    echo "No tagged images found in repository"
    exit 1
fi

# Use dialog to select tag
SELECTED=$(echo "$TAGS" | dialog --menu "Select image to pull:" 20 60 10 $(echo "$TAGS" | nl -w2 -s' ' | sed 's/\t/ /g') 3>&1 1>&2 2>&3)

if [ $? -eq 0 ] && [ -n "$SELECTED" ]; then
    TAG=$(echo "$TAGS" | sed -n "${SELECTED}p")
    echo "Pulling $ECR_URI:$TAG"
    docker pull $ECR_URI:$TAG
fi