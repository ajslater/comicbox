#!/bin/bash
set -euo pipefail
poetry run isort --check-only --color .
poetry run black --check .
