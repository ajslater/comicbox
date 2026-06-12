#!/usr/bin/env bash
# Sort all ignore files in place and remove duplicates.
# Comment lines are hoisted (in original order) to a header block:
# sorting them alphabetically into the patterns scrambled multi-line
# comments and detached them from everything they described.
set -euo pipefail
# Set locale to make output deterministic across shells
export LC_ALL=en_US.UTF-8
for f in .*ignore; do
  if [ -L "$f" ]; then
    continue
  fi
  tmp="$(mktemp)"
  { grep '^#' "$f" || true; } >"$tmp"
  # Strip trailing slashes so dir/non-dir variants (dist, dist/) dedupe.
  { grep -v '^#' "$f" || true; } | sed -e 's:/$::' -e '/^$/d' | sort --unique >>"$tmp"
  mv "$tmp" "$f"
  echo "$f" sorted
done
