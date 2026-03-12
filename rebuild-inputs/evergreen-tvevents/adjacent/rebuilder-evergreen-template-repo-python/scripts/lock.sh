#!/usr/bin/env bash
set -eu pipefail

echo "Locking pip, pip-tools, & setup tools..."
pip install --no-cache-dir --upgrade -qqq pip==24.3.1 setuptools==78.1.1 pip-tools==7.5.0
echo "Locking production requirements..."
pip-compile pyproject.toml -o requirements.txt --generate-hashes --strip-extras --quiet
echo "Locking development requirements..."
pip-compile pyproject.toml --extra=dev -o requirements-dev.txt --generate-hashes --strip-extras --allow-unsafe --quiet
