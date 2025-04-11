"""Validator cli."""

import sys
from pathlib import Path

from tests.validate.validate import FMT_VALIDATOR_MAP, guess_format, validate_path


def main(argv):
    """Run validation with helpful print output."""
    if len(argv) > 1:
        path = Path(argv[1])
    else:
        reason = "no path given"
        raise ValueError(reason)
    fmt = argv[2] if len(argv) > 2 else ""  # noqa: PLR2004
    if not fmt:
        fmt = guess_format(path)
    print(f"Format: {fmt}")
    validator = FMT_VALIDATOR_MAP[fmt]
    if isinstance(validator, str):
        print(validator)
    else:
        print("Schema:", validator.schema_path.name)
    validate_path(path, fmt)
    print("Valid.")


if __name__ == "__main__":
    main(sys.argv)
