#!/bin/bash
# Validate comic metadata schemas
# args: <filename> [comicbox format code]
set -euo pipefail
PYTHONPATH=. uv run python tests/validate/cli.py "$@"
