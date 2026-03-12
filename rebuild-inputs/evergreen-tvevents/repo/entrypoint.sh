#!/bin/bash
set -eu

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

if [ ! -f "$BLACKLIST_CHANNEL_IDS_CACHE_FILEPATH" ]; then
  printf "Cache file not found. Initializing...\n"
  python -c "from app.dbhelper import TvEventsRds; TvEventsRds().initialize_blacklisted_channel_ids_cache()" || \
  printf "Cache initialization failed, continuing...\n"
fi

printf "Starting Gunicorn Server...\n"

exec gunicorn -w "${WEB_CONCURRENCY:-3}" -b [::]:8000 "app:create_app()" \
  --capture-output \
  --log-level="$LOG_LEVEL" \
  -k gevent \
  --worker-connections=500 \
  --max-requests 100000 \
  --max-requests-jitter 100
