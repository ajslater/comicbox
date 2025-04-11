#!/bin/bash
# Publish the created package
set -euo pipefail
cd "$(dirname "$0")/.."
UV_PUBLISH_TOKEN=$PYPI_PASS uv publish
