#!/bin/bash
# Publish the created package
set -euo pipefail
cd "$(dirname "$0")/.."
pip3 install --upgrade pip
pip3 install --upgrade poetry
poetry publish -u "$PYPI_USER" -p "$PYPI_PASS"
