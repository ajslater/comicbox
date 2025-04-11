#!/bin/bash
# Convert a poetry project to uv
set -euo pipefail
echo "Changing build dependencies to hatchling..."
poetry add -D hatchling toml-cli
poetry remove wheel || true

echo "Convrting pyproject.toml..."
uv run pdm import pyproject.toml

TOML_PATH=--toml-path=pyproject.toml
printf "\tSaving build configuration..."
BUILD_INCLUDE=$(uv run toml get "$TOML_PATH" tool.pdm.build.includes) || true
BUILD_EXCLUDE=$(uv run toml get "$TOML_PATH" tool.pdm.build.excludes) || true
printf "\tRemoving old sections..."
uv run toml unset "$TOML_PATH" tool.pdm
uv run toml unset "$TOML_PATH" tool.poetry
printf "\tConfigure new build system..."
uv run toml add_section "$TOML_PATH" build-system
uv run toml set "$TOML_PATH" build-system.requires --to-array '["hatchling"]'
uvx toml set "$TOML_PATH" build-system.build-backend hatchling.build
uv run toml add_section "$TOML_PATH" tool.hatch.build.targets.sdist
uv run toml set "$TOML_PATH" tool.hatch.build.targets.sdist.include --to-array "$BUILD_INCLUDE"
uv run toml set "$TOML_PATH" tool.hatch.build.targets.sdist.exclude --to-array "$BUILD_EXCLUDE"
echo "Configure pyright for venv..."
uv run toml set "$TOML_PATH" tool.pyright.venvPath '.'
uv run toml set "$TOML_PATH" tool.pyright.venv '.venv'

CCI_CONFIG=.circleci/config.yml
if [ -f "$CCI_CONFIG" ]; then
  echo "Configure circleci for uv..."
  uv run yq eval '.jobs.deploy.docker[0].image =  ghcr.io/astral-sh/uv:bookworm-slim' -i "$CCI_CONFIG"
  uv run yq eval '.jobs.deploy.steps[1].run = uv publish' -i "$CCI_CONFIG"
fi

echo "Remove old files..."
rm -rf builder-requirements.txt bin/update-builder-requirement.sh bin/publish-pypi.sh __pycache__ .venv uv.lock poetry.lock
echo "Replace referenecs to poetry.lock with uv.lock"
find . \( -path "./bin" -o -path "./node_modules" -o -path "./frontend" -o -path "./test-results" -o -path "./.git" -o -path "./.venv" \) -prune -o -type f -exec sed -i '' -e 's/poetry.lock/uv.lock/g' {} \;

echo "Update project dependencies"
uv sync --all-extras --no-install-project

echo "Done!"
echo

echo 1. Bin Scripts
echo 1.1 Copy new bin scripts from boilerplate
echo 1.2. Activate hadolint &
circlecicheck in bin/lint-backend.sh if appropriate.
echo 1.3. Diff new bin scripts.
echo 2. Fix Makefile from boilerplate.
echo 3. Build config
echo 3.1 Fix docker-compose.yaml
echo 3.2. Fix Dockerfiles to use nikolaik/python-nodejs
echo 3.3. Create new token on pypi for circleci
echo 4. Project File
echo 4.1. Format &
order pyproject.toml
echo 4.2. Fix versions to use tilde versions where appropriate.
