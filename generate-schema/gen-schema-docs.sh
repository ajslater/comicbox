#!/usr/bin/env bash
# Generate markdown docs for the comicbox JSON and XML schemas into docs/schema
set -euo pipefail
cd "$(dirname "$0")/.."
SCHEMA_VERSION=3.0
READING_LIST_VERSION=1.0
DEST=docs/schema
# The comicbox schema's pages share a directory whose index page is the root
# schema, so the docs nav lists the sub-schemas under it. The reading-list
# schema does the same.
COMICBOX_DEST=$DEST/comicbox-v$SCHEMA_VERSION
READING_LIST_DEST=$DEST/reading-list-v$READING_LIST_VERSION

gen() {
  # Render the JSON schema $1 as the markdown page $2.
  local path=$1 md=$2
  uvx jsonschema2md@1.7.0 --locale en_US "$path" "$md"
  # jsonschema2md can't link bare relative $refs, point them at the sibling pages,
  # and the reading-list schema's refs into v3.0 at the Comicbox 3.0 pages.
  perl -pi -e 's|\(:///([\w.-]+)\.schema\.json#\)|($1.schema.md)|g' "$md"
  perl -pi -e 's|\(:///\.\./\.\./v[\d.]+/([\w.-]+)\.schema\.json#\)|(../comicbox-v'"$SCHEMA_VERSION"'/$1.schema.md)|g' "$md"
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
mkdir -p "$READING_LIST_DEST"
for path in comicbox/schemas/reading-list/v"$READING_LIST_VERSION"/*.schema.json; do
  name=$(basename "$path" .json)
  if [[ $name == reading-list-v* ]]; then
    gen "$path" "$READING_LIST_DEST/index.md"
    V=$READING_LIST_VERSION perl -pi -e 'if ($. == 1) { s/^# Reading List$/# Reading List $ENV{V}/ }' "$READING_LIST_DEST/index.md"
  else
    gen "$path" "$READING_LIST_DEST/$name.md"
  fi
done
gen comicbox/schemas/comic-book-info-v1.0.schema.json "$DEST/comic-book-info-v1.0.schema.md"
# json-cbl is vendored from its upstream; say where from under the title.
JSON_CBL_MD=$DEST/json-cbl-v1.0.schema.md
gen comicbox/schemas/json-cbl-v1.0.schema.json "$JSON_CBL_MD"
perl -0pi -e 's|\A(# [^\n]*\n)|$1\nVendored byte for byte from [json-cbl-standard](https://github.com/ComicReadingLists/json-cbl-standard), [schema/1.0/comic-reading-list.schema.json](https://github.com/ComicReadingLists/json-cbl-standard/blob/dea268c508b9/schema/1.0/comic-reading-list.schema.json) at commit `dea268c` (2024-09-03).\n|' "$JSON_CBL_MD"
# The filename schema ships inside comicfn2dict. Render it from the installed
# package, then title it and add the keys comicbox keeps.
FILENAME_MD=$DEST/comicfn2dict.schema.md
gen "$(uv run generate-schema/filename_docs.py --schema-path)" "$FILENAME_MD"
uv run generate-schema/filename_docs.py "$FILENAME_MD"
uv run generate-schema/xsd_docs.py
npx prettier --write "$DEST"
