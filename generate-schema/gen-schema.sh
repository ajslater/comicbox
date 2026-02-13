#!/bin/bash
# Generate jsonschema from marshmallwo
set -euo pipefail
./mjs.py
FN=generated.schema.json
npx eslint --fix "$FN"
perl -pi -e 's|"title":.*?,||g' "$FN"
