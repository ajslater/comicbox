#!/bin/bash
set -euxo pipefail
if [ "${1:-}" = "-f" ]; then
    # Fix before check
    ./fix-lint.sh
fi
poetry run flake8 .
poetry run isort --check-only --color .
poetry run black --check .
poetry run pyright .
poetry run vulture .
prettier --check .
shellcheck -x ./*.sh ./**/*.sh
shfmt -d -i 4 ./*.sh ./**/*.sh
# hadolint build.Dockerfile
