#!/bin/bash
# Replace export archive for testing.
set -euo pipefail
FN=../export.cbz
../create-archive.sh "$FN"
