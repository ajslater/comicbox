#!/usr/bin/env bash
# Generate markdown docs for the comicbox v3.0 JSON schemas into site/schema
set -euo pipefail
cd "$(dirname "$0")/.."
SRC=comicbox/schemas/v3.0
DEST=site/schema
for path in "$SRC"/*.schema.json; do
  md="$DEST/$(basename "$path" .json).md"
  uvx jsonschema2md@1.7.0 --locale en_US "$path" "$md"
  # jsonschema2md can't link bare relative $refs, point them at the sibling pages.
  perl -pi -e 's|\(:///([\w.-]+)\.schema\.json#\)|($1.schema.md)|g' "$md"
done
npx prettier --write "$DEST"
