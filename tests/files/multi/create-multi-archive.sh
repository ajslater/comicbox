#!/bin/bash
# Replace export archive for testing.
set -euo pipefail
FN=../$(cat comicbox-filename.txt)
../create-archive.sh "$FN"
