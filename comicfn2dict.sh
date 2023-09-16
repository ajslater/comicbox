#!/bin/bash
# Run comicbox file parser test
set -euo pipefail
poetry run ./comicfn2dict.py "$@"
