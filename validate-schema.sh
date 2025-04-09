#!/bin/bash
set -euo pipefail
PYTHONPATH=. uv run python "$@"
