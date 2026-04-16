#!/usr/bin/env bash
# Run all tests
set -euxo pipefail
mkdir -p test-results
#uv run --python 3.13 --group test --extra pdf \
#  -m righttyper --include-files 'comicbox/*' --overwrite --output-files --python-version 3.10 \
#  -m pytest
LOGLEVEL=DEBUG uv run --group test --extra pdf pytest "$@"
# pytest-cov leaves .coverage.$HOST.$PID.$RAND files around while coverage itself doesn't
uv run --group test coverage erase || true
