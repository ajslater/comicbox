#!/bin/bash
set -euxo pipefail
if [ "${1:-}" = "-f" ]; then
    # Fix before check
    ./fix-lint.sh
fi
poetry run pytest --ignore=tests .
poetry run pyright .
poetry run vulture .
poetry run radon mi -nc . || true
npx prettier --check .
shellcheck -x ./*.sh ./**/*.sh
# hadolint build.Dockerfile
if [ "$(uname)" = "Darwin" ]; then
    # shellcheck disable=2035
    hadolint *Dockerfile
    shfmt -d -i 4 ./*.sh ./**/*.sh
    circleci config check .circleci/config.yml
fi
poetry run codespell .
