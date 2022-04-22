#!/bin/bash
# Local test of ci
set -euo pipefail
docker compose build comicbox-builder
./docker/docker-compose-exit.sh comicbox-test
./docker/docker-compose-exit.sh comicbox-lint
./docker/docker-compose-exit.sh comicbox-build
