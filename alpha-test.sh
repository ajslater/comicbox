#!/bin/bash
set -euo pipefail
./build-builder.sh
./docker/docker-compose-exit.sh comicbox-test
./docker/docker-compose-exit.sh comicbox-lint
./docker/docker-compose-exit.sh comicbox-build
