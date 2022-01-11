#!/bin/bash
# Run all fixes and then all tests & lints.
# Good to do before commits
set -euo pipefail
./fix-lint.sh
./test.sh
./lint.sh
