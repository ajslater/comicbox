#!/bin/bash
set -euxo pipefail
poetry run isort --color .
poetry run black .
prettier --write .
shfmt -s -w -i 4 ./*.sh ./**/*.sh
