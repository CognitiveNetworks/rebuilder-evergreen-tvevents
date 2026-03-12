#!/bin/bash
set -e

NAMESPACE="demo-app-loop-dev-$(echo $USER | tr '.' '-')"

echo ""
echo "=== HTTPRoute Information ==="
kubectl get httproute -n $NAMESPACE -o wide
