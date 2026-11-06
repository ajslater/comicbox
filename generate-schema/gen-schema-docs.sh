#!/usr/bin/env bash
# Generate markdown docs for the comicbox JSON and XML schemas into docs/schema
set -euo pipefail
cd "$(dirname "$0")/.."
SCHEMA_VERSION=3.0
DEST=docs/schema
# The comicbox schema's pages share a directory whose index page is the root
# schema, so the docs nav lists the sub-schemas under it.
COMICBOX_DEST=$DEST/comicbox-v$SCHEMA_VERSION

gen() {
  # Render the JSON schema $1 as the markdown page $2.
  local path=$1 md=$2
  uvx jsonschema2md@1.7.0 --locale en_US "$path" "$md"
  # jsonschema2md can't link bare relative $refs, point them at the sibling pages.
  perl -pi -e 's|\(:///([\w.-]+)\.schema\.json#\)|($1.schema.md)|g' "$md"
  # The H1 is the page's docs nav title. Drop the "Comicbox " prefix that every
  # sub-schema title repeats and give the root schema its version.
  V=$SCHEMA_VERSION perl -pi -e 'if ($. == 1) { s/^# Comicbox (.+)/# $1/ or s/^# Comicbox$/# Comicbox $ENV{V}/ }' "$md"
}

mkdir -p "$COMICBOX_DEST"
for path in comicbox/schemas/v"$SCHEMA_VERSION"/*.schema.json; do
  name=$(basename "$path" .json)
  if [[ $name == comicbox-v* ]]; then
    gen "$path" "$COMICBOX_DEST/index.md"
  else
    gen "$path" "$COMICBOX_DEST/$name.md"
  fi
done
gen comicbox/schemas/comic-book-info-v1.0.schema.json "$DEST/comic-book-info-v1.0.schema.md"
uv run generate-schema/xsd_docs.py
npx prettier --write "$DEST"
