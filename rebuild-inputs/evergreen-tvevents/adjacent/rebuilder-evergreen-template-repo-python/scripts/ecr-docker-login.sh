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


#!/bin/bash

if [ "$1" = "--clean" ]; then
    timestamp=$(date +%Y%m%d-%H%M%S)
    [ -d ~/.aws/sso ] && mv ~/.aws/sso ~/.aws/sso-bak-$timestamp && echo "Backed up ~/.aws/sso"
    [ -f ~/.kube/config ] && mv ~/.kube/config ~/.kube/config-bak-$timestamp && echo "Backed up ~/.kube/config"
fi

profiles="inscape-evergreen-dev"
regions="us-east-1"

# Check if running in kubie shell and re-exec in clean environment
if [ -n "$KUBIE_SHELL" ]; then
    echo "Detected kubie shell. Re-executing in clean shell..."
    exec env -i HOME="$HOME" PATH="$PATH" AWS_PROFILE="$AWS_PROFILE" /bin/bash "$0" "$@"
fi

for profile in $profiles; do
    echo "Logging in with profile: $profile"
    AWS_PROFILE=$profile aws sso login

    for region in $regions; do
        clusters=$(AWS_PROFILE=$profile aws eks list-clusters --region $region --query 'clusters[]' --output text 2>/dev/null)

        if [ -n "$clusters" ]; then
            for cluster in $clusters; do
                echo "Updating kubeconfig for $cluster in $region"
                AWS_PROFILE=$profile aws eks update-kubeconfig --name $cluster --region $region
            done
        fi
    done
done

kubectl config set-credentials "e7n-authz" \
  --exec-api-version=client.authentication.k8s.io/v1beta1 \
  --exec-command=kubelogin \
  --exec-arg=get-token \
  --exec-arg=--environment \
  --exec-arg=AzurePublicCloud \
  --exec-arg=--server-id \
  --exec-arg=f198091a-4c4e-4bbc-afc5-a51f25bca427 \
  --exec-arg=--client-id \
  --exec-arg=f198091a-4c4e-4bbc-afc5-a51f25bca427 \
  --exec-arg=--tenant-id \
  --exec-arg=de6e8d9c-bdf8-4e1d-9540-8bc6cb9cda82

for context in $(kubectl config get-contexts -o name); do
    kubectl config set-context "$context" --user=e7n-authz
done



# Get repository URI
ECR_URI=$(aws ecr describe-repositories --repository-names $REPO_NAME --region $REGION --query 'repositories[0].repositoryUri' --output text)

# Login to Docker
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ECR_URI

echo "Connected to repository: $ECR_URI"
echo "Docker logged in successfully"

# Verify repository exists
echo "Verifying repository..."
aws ecr describe-repositories --repository-names $REPO_NAME --region $REGION --query 'repositories[0].[repositoryName,createdAt]' --output table