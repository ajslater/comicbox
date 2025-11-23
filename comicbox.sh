#!/bin/bash
# Run comicbox in development
set -euo pipefail
export PYTHONDEVMODE=1
uv run ./comicbox.py "$@"
