#!/usr/bin/env bash
# Lint complexity
set -euo pipefail
# No platform guard: complexipy and radon are pure-Python and must run
# in CI too — the old Darwin-only guard silently skipped complexity
# linting everywhere but the maintainer's laptop.
uv run --group lint complexipy
uv run --group lint radon mi --min B .
uv run --group lint radon cc --min C .
