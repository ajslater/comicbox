#!/bin/bash
set -euo pipefail
pip3 install --upgrade pip
pip3 install --upgrade poetry
poetry install --no-root
npm install
