#!/bin/bash
set -euo pipefail
pip3 install -U poetry
poetry install --no-root
npm install -g prettier prettier-plugin-toml
