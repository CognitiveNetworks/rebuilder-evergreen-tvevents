#!/bin/bash
# Test Helm template rendering with all values files
# Usage: ./test-helm-template.sh [template-name|-all]
# Example: ./test-helm-template.sh HTTPRoute.yaml
#          ./test-helm-template.sh Deployment.yaml
#          ./test-helm-template.sh -all (renders all templates, shows resource kinds)
#          ./test-helm-template.sh (renders all templates with full output)

set -e

CHART_DIR="charts"
TEMPLATE="${1:-}"
VALUES_FILES=(
  "values-mvp.yaml"
)

# Build values file arguments
VALUES_ARGS=""
for file in "${VALUES_FILES[@]}"; do
  if [ -f "$CHART_DIR/$file" ]; then
    VALUES_ARGS="$VALUES_ARGS --values $CHART_DIR/$file"
  fi
done

# Common helm args (infrastructure config only)
COMMON_ARGS="
  --set ciOptions.cloud_region=us-east-1
  --set ciOptions.aws_account_id=123456789
  --set otelcollector.enabled=false
"

# Build show-only argument if template specified
SHOW_ONLY=""
if [ -n "$TEMPLATE" ] && [ "$TEMPLATE" != "-all" ]; then
  SHOW_ONLY="--show-only templates/$TEMPLATE"
fi

helm lint $CHART_DIR \
    $VALUES_ARGS \
    --set ciOptions.workload_env=true \
    --set ciOptions.environment=dev \
    $COMMON_ARGS

# If -all flag, render all templates and show full output
if [ "$TEMPLATE" = "-all" ]; then
  echo "=== Rendering all templates (dev environment) ==="
  helm template demo-app $CHART_DIR \
    $VALUES_ARGS \
    --set ciOptions.workload_env=true \
    --set ciOptions.environment=dev \
    $COMMON_ARGS
  exit 0
fi

# Test different environments
echo "=== Testing workload_env (dev) ==="
helm template demo-app $CHART_DIR \
  $VALUES_ARGS \
  --set ciOptions.workload_env=true \
  --set ciOptions.environment=dev \
  --set environmentConfig.dev.deployments.demo-app.sha_ref=sha-ref-xyz \
  $COMMON_ARGS \
  $SHOW_ONLY

echo ""
echo "=== Testing workload_env (qa) ==="
helm template demo-app $CHART_DIR \
  $VALUES_ARGS \
  --set ciOptions.workload_env=true \
  --set ciOptions.environment=qa \
  --set environmentConfig.qa.deployments.demo-app.sha_ref=sha-ref-xyz \
  $COMMON_ARGS \
  $SHOW_ONLY

echo ""
echo "=== Testing workload_env (prod) ==="
helm template demo-app $CHART_DIR \
  $VALUES_ARGS \
  --set ciOptions.workload_env=true \
  --set ciOptions.environment=prod \
  --set environmentConfig.prod.deployments.demo-app.sha_ref=sha-ref-xyz \
  $COMMON_ARGS \
  $SHOW_ONLY

echo ""
echo "=== Testing pr_env ==="
helm template demo-app $CHART_DIR \
  $VALUES_ARGS \
  --set ciOptions.pr_number=123 \
  --set ciOptions.environment=pr-123 \
  --set environmentConfig.pr-123.deployments.demo-app.sha_ref=sha-ref-xyz \
  $COMMON_ARGS \
  $SHOW_ONLY
