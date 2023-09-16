#!/bin/bash
# Validate schemas
set -euo pipefail
JSON_SCHEMA=schemas/comicbox.schema.json
JSON=tests/test_files/metadata/comicbox.json
echo Validate "$JSON_SCHEMA"
poetry run check-jsonschema --check-metaschema "$JSON_SCHEMA"
echo Validate "$JSON"
poetry run check-jsonschema --schemafile "$JSON_SCHEMA" "$JSON"
