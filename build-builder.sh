#!/bin/bash
set -euo pipefail
# Build pip installable wheel and sdist files from build.Dockerfile
source .env.build
export DOCKER_CLI_EXPERIMENTAL=enabled
export DOCKER_BUILDKIT=1
export CODEX_BUILDER_BASE_VERSION
docker-compose build comicbox-builder
