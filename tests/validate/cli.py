"""Validator cli."""

import sys
from pathlib import Path

from tests.validate.validate import guess_format, validate_path

argv = sys.argv
if len(argv) > 1:
    path = Path(argv[1])
else:
    reason = "no path given"
    raise ValueError(reason)
fmt = argv[2] if len(argv) > 2 else ""  # noqa: PLR2004
if not fmt:
    fmt = guess_format(path)
print(f"Format {fmt}")
validate_path(path, fmt)
print("Valid.")
