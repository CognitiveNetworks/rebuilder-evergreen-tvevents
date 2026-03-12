#!/bin/bash
set -eu pipefail

source /usr/local/bin/environment-check.sh

AWS_CONFIG_FILE="$HOME/.aws/config"
mkdir -p "$HOME/.aws"

cat <<EOL > "$AWS_CONFIG_FILE"
[default]
output = json
region = $AWS_REGION
EOL

printf "AWS config file created at %s\n" "$AWS_CONFIG_FILE"


export OTEL_PYTHON_AUTO_INSTRUMENTATION_ENABLED="$OTEL_PYTHON_AUTO_INSTRUMENTATION_ENABLED"
printf "OTEL Auto Instrumentation set to %s\n" "$OTEL_PYTHON_AUTO_INSTRUMENTATION_ENABLED"

if [ "$OTEL_PYTHON_AUTO_INSTRUMENTATION_ENABLED" = "true" ]; then
    printf "Configuring OTEL...\n"

    export OTEL_SDK_DISABLED=false
    export OTEL_EXPORTER_OTLP_HEADERS="api-key=${OTEL_EXPORTER_OTLP_HEADERS}"

    printf "OTEL SERVICE NAME: %s\n" "$SERVICE_NAME"
fi

printf "Starting Uvicorn Server...\n"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level debug --reload

