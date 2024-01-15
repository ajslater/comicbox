#!/bin/bash
# Update archives with new metadata
set -euo pipefail

# zip -9 ../cli.cbz comicbox.yaml
zip -9 ../comicbox-cli.cbz comicbox-cli.yaml
zip -9 ../comicbox.cbz comicbox.json
zip -9 ../comictagger.cbz comictagger.json
zip -9 ../xml.cbz comicbox.xml
zip -9 ../yaml.cbz comicbox.yaml
zip -9 "../Captain Science #001-metron.cbz" metroninfo.xml

tar czf "../Captain Science #001-cix.cbt" "../Captain Science 001"/*0[1-5].jpg comicinfo.xml

rar a "../Captain Science #001-cix-cbi.cbr" comicinfo.xml
rar c -z./comic-book-info.json "../Captain Science #001-cix-cbi.cbr"
rar c -z./comic-book-info.json "../Captain Science #001-cbi.cbr"

cd ..
zip -9 "Captain Science #001-cix.cbz" "Captain Science 001/comicinfo.xml"
