#!/usr/bin/env bash
# Generate markdown docs for the comicbox JSON schemas into docs/schema
set -euo pipefail
cd "$(dirname "$0")/.."
SCHEMA_VERSION=3.0
DEST=docs/schema
for path in comicbox/schemas/v"$SCHEMA_VERSION"/*.schema.json comicbox/schemas/comic-book-info-v1.0.schema.json; do
  md="$DEST/$(basename "$path" .json).md"
  uvx jsonschema2md@1.7.0 --locale en_US "$path" "$md"
  # jsonschema2md can't link bare relative $refs, point them at the sibling pages.
  perl -pi -e 's|\(:///([\w.-]+)\.schema\.json#\)|($1.schema.md)|g' "$md"
  # The H1 is the page's docs nav title. Drop the "Comicbox " prefix that every
  # sub-schema title repeats and give the root schema its version.
  V=$SCHEMA_VERSION perl -pi -e 'if ($. == 1) { s/^# Comicbox (.+)/# $1/ or s/^# Comicbox$/# Comicbox $ENV{V}/ }' "$md"
done
npx prettier --write "$DEST"
