#!/bin/bash
# Run comicbox in development
set -euo pipefail
poetry run ./comicbox.py "$@"
