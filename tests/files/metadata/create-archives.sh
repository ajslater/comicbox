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
zip -9 "../Captain Science #001.cbz" comicinfo.xml
zip -9 "../Captain Science #001-cix.cbz" comicinfo.xml

rar a "../Captain Science #001-cix-cbi.cbr" comicinfo.xml
rar c -m5 -z./comic-book-info.json "../Captain Science #001-cix-cbi.cbr"
rar c -m5 -z./comic-book-info.json "../Captain Science #001-cbi.cbr"

cd ..
zip -9 "Captain Science #001-cix.cbz" "Captain Science 001/comicinfo.xml"
