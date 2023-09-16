#!/bin/bash
# Local test of ci
set -euo pipefail
docker compose build comicbox-builder
./bin/docker-compose-exit.sh comicbox-test
./bin/docker-compose-exit.sh comicbox-lint
./bin/docker-compose-exit.sh comicbox-build
