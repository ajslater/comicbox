"""Validator cli."""

import sys
from pathlib import Path

from comicbox.box.validate import validate_source
from comicbox.box.validate.guess_format import guess_format


def main(argv):
    """Run validation with helpful print output."""
    if len(argv) > 1:
        path = Path(argv[1])
    else:
        reason = "no path given"
        raise ValueError(reason)
    if len(argv) > 2:  # noqa: PLR2004
        fmt_str = argv[2]
        fmt = guess_format(fmt_str)
    else:
        fmt = None
    validate_source(path, fmt=fmt)
    print("Valid.")  # noqa: T201


if __name__ == "__main__":
    main(sys.argv)
