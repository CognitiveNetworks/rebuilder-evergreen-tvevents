#!/bin/bash
# RDS Variables
rds_vars=()

# Always required
always_required_vars=(
  ENV
  LOG_LEVEL
  AWS_REGION
  TEST_CONTAINER
  SERVICE_NAME
  OTEL_PYTHON_AUTO_INSTRUMENTATION_ENABLED
)

# OTEL/NR tracing
otel_nr_vars=(
  OTEL_PYTHON_LOG_FORMAT
  OTEL_EXPORTER_OTLP_HEADERS
  OTEL_EXPORTER_OTLP_PROTOCOL
  OTEL_PYTHON_LOG_CORRELATION
  OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT
  OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST
  OTEL_EXPORTER_OTLP_COMPRESSION
)

# Track unset variables
unset_vars=()

if [ -z "${ENV:-}" ]; then
  printf "Error: ENV environment variable is not set and is required.\n"
  exit 1
fi

# ENV must be set to dev if TEST_CONTAINER is true
if [ "${TEST_CONTAINER,,}" = "true" ]; then
  if [ "${ENV}" != "dev" ]; then
    printf "\nError: TEST_CONTAINER can only be enabled if ENV is set to dev (ENV='%s')\n" "${ENV}"
    exit 1
  else
    printf "\nTEST_CONTAINER is enabled and container is in dev env. Turning off OTEL...\n"
    export OTEL_SDK_DISABLED=true
    export OTEL_PYTHON_AUTO_INSTRUMENTATION_ENABLED=false
  fi
else
  # Check all RDS vars
  for var in "${rds_vars[@]}"; do
    if [ -z "${!var:-}" ]; then
      unset_vars+=("$var")
    fi
  done

  # --- OTEL/NR tracing check ---
  if [ "${OTEL_PYTHON_AUTO_INSTRUMENTATION_ENABLED,,}" = "true" ]; then
    for var in "${otel_nr_vars[@]}"; do
      if [ -z "${!var:-}" ]; then
        unset_vars+=("$var")
      fi
    done

    if [[ "${LOG_LEVEL,,}" == "debug" ]]; then
      export OTEL_PYTHON_DEBUG=true
      export OTEL_LOG_LEVEL=debug
    else
      export OTEL_PYTHON_DEBUG=false
      export OTEL_LOG_LEVEL=info
    fi
  fi
fi

# Check always required variables.
for var in "${always_required_vars[@]}"; do
  if [ -z "${!var:-}" ]; then
    unset_vars+=("$var")
  fi
done

if [ ${#unset_vars[@]} -ne 0 ]; then
  printf "\nError: The following environment variables are not set:\n"
  for var in "${unset_vars[@]}"; do
    printf "\n- %s" "$var"
  done
  exit 1
else
  printf "\nAll required environment variables are set. Proceeding...\n"
fi