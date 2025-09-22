#!/bin/bash
# Run comicbox in development
set -euo pipefail
uv run ./comicbox.py "$@"
