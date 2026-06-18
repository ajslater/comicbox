#!/usr/bin/env bash
# Validate a comic metadata instance file against a schema.
# args: <schemafile> <instancefile>
set -euo pipefail
BASE_URI=$(readlink -f "$(dirname "$0")/schemas/v2.0")/
check-jsonschema --base-uri="$BASE_URI" --schemafile "${1:?usage: check-jsonschema.sh <schemafile> <instancefile>}" "${2:?usage: check-jsonschema.sh <schemafile> <instancefile>}"
