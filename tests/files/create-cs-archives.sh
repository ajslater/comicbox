#!/bin/bash
# create a couple simple comic archives from the dir.
DIR="Captain Science 001"
STEM="Captain Science #001"
rm -f "$DIR/*~"
zip -9 -r "${STEM}.cbz" "$DIR"
7zz a -mx9 -r "${STEM}.cb7" "$DIR"
tar cJf "${STEM}-cix.cbt" "$DIR"
