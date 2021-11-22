#!/bin/bash
set -euo pipefail
poetry run isort --color .
poetry run black .
prettier --write .
shfmt -s -w -i 4 ./*.sh ./**/*.sh
