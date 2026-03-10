#!/usr/bin/env bash
set -euo pipefail

# pip-compile workflow: pyproject.toml → requirements.txt
# Usage: ./scripts/lock.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "[lock] Compiling requirements.txt from pyproject.toml..."
pip-compile \
    --generate-hashes \
    --output-file="${PROJECT_DIR}/requirements.txt" \
    "${PROJECT_DIR}/pyproject.toml"

echo "[lock] Compiling requirements-dev.txt from pyproject.toml [dev]..."
pip-compile \
    --extra=dev \
    --generate-hashes \
    --output-file="${PROJECT_DIR}/requirements-dev.txt" \
    "${PROJECT_DIR}/pyproject.toml"

echo "[lock] Done."
