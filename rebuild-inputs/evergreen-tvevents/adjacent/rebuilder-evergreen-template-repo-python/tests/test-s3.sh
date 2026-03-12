#!/bin/bash
# =================================================================
# TEST DAPR S3 INTEGRATION
# =================================================================
#
# Purpose:
#   Validates Dapr S3 binding integration by testing upload and download.
#   Ensures application can communicate with Dapr sidecar and S3.
#
# Usage:
#   ./test-s3.sh <url>
#
# Arguments:
#   url: Application base URL (e.g., http://demo-app.dev.evergreen.cognet.tv)
#
# Example:
#   ./test-s3.sh http://demo-app-loop-dev-bryan-taylor.dev.evergreen.tvinteractive.tv
#
# Test Flow:
#   1. POST /s3/upload with JSON: {"key": "test.txt", "data": "hello from dapr"}
#   2. GET /s3/download/test.txt
#   3. Verify downloaded content matches uploaded content
#
# What This Tests:
#   - Dapr sidecar is running and accessible at localhost:3500
#   - DaprComponent CRD is correctly configured
#   - S3 credentials are valid and accessible from Kubernetes secret
#   - Application can POST to Dapr binding endpoint
#   - Application can GET from Dapr binding endpoint
#   - S3 bucket permissions allow PutObject and GetObject
#
# Expected Output:
#   ✅ S3 integration test passed!
#
# Troubleshooting:
#   - 404 Not Found: Check Dapr sidecar injection (dapr.io/enabled: "true")
#   - 500 Internal Server Error: Check Dapr component logs
#   - Connection refused: Check pod has Dapr sidecar container
#   - Access denied: Check S3 credentials in Kubernetes secret
#   - Bucket not found: Check bucket name in values-dapr.yaml
#
# Dapr Architecture:
#   Application → localhost:3500 → Dapr Sidecar → AWS S3
#   
#   Application calls:
#     POST localhost:3500/v1.0/bindings/s3-bucket
#   
#   Dapr translates to:
#     AWS S3 PutObject API call
#
# Dependencies:
#   - curl: HTTP client for testing
#   - Application must be deployed with Dapr enabled
#   - S3 bucket must exist and be accessible
#
# =================================================================
set -e

if [ -z "$1" ]; then
  echo "Usage: $0 <url>"
  echo "Example: $0 http://your-app.dev.evergreen.cognet.tv"
  exit 1
fi

URL="$1"

echo "Testing Dapr S3 integration..."
echo ""

echo "1. Uploading test.txt to S3..."
UPLOAD_RESPONSE=$(curl -s -X POST "$URL/s3/upload" \
  -H "Content-Type: application/json" \
  -d '{"key": "test.txt", "data": "hello from dapr"}')
echo "Response: $UPLOAD_RESPONSE"
echo ""

echo "2. Downloading test.txt from S3..."
DOWNLOAD_RESPONSE=$(curl -s "$URL/s3/download/test.txt")
echo "Response: $DOWNLOAD_RESPONSE"
echo ""

if [ "$DOWNLOAD_RESPONSE" = "hello from dapr" ]; then
  echo "✅ S3 integration test passed!"
else
  echo "❌ S3 integration test failed!"
  exit 1
fi
