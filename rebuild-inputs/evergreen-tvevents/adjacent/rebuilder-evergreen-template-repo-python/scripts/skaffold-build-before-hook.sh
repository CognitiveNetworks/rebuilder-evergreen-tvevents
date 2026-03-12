#!/bin/bash
set -e

AWS_PROFILE=inscape-evergreen-dev ./scripts/ecr-docker-login.sh inscape-infra-dev-demo-app us-east-1


kubectl delete jobs --all -n demo-app-loop-dev-$(echo $USER | tr '.' '-') --ignore-not-found=true
