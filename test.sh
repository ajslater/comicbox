#!/bin/bash
set -euxo pipefail
mkdir -p test-results
poetry run pytest -vvv
# pytest-cov leaves .coverage.$HOST.$PID.$RAND files around while coverage itself doesn't
poetry run coverage erase
poetry run vulture .
poetry run radon mi -nc .
