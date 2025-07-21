#!/bin/bash
# Validate comic metadata schemas
# args: <filename> [comicbox format code]
set -euox pipefail
BASE_URI=$(readlink -f "$(dirname "$0")/schemas/v2.0")/
check-jsonschema --base-uri="$BASE_URI" --schemafile "$1" "$2"
