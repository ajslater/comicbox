#!/bin/bash
# Update python and npm dependencies
source .venv/bin/activate
set -euo pipefail
poetry update
poetry show --outdated
npm update
npm outdated
