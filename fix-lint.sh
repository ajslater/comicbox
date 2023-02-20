#!/bin/bash
set -euxo pipefail
poetry run ruff --fix .
poetry run black .
prettier --write .
# shfmt -s -w -i 4 ./*.sh ./**/*.sh
shellharden --replace ./*.sh ./**/*.sh
