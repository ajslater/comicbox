#!/bin/bash
set -euxo pipefail
mkdir -p test-results
LOGLEVEL=DEBUG poetry run pytest
# pytest-cov leaves .coverage.$HOST.$PID.$RAND files around while coverage itself doesn't
poetry run coverage erase || true
poetry run vulture . || true
poetry run radon mi -nc . || true
