#!/bin/bash
# Create a test archive from the metadata files.
set -euo pipefail
FN=$1
FILES=(
  comet.xml comicbox-cli.yaml comicbox.yaml comictagger.json
  comicbox.json comicinfo.xml
)
rm -f "$FN"
zip -9 "$FN" "${FILES[@]}" -z < comic-book-info.json
echo Created "$FN"
