#!/bin/bash
set -euo pipefail
poetry run flake8 .
poetry run isort --check-only --color .
poetry run black --check .
poetry run pyright .
poetry run vulture .
prettier --check .
shellcheck -x ./*.sh ./ci/*.sh
# hadolint build.Dockerfile
