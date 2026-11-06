#!/usr/bin/env python3
"""
The filename schema page: comicfn2dict's schema, with what comicbox keeps.

comicfn2dict ships the schema in its wheel. ``--schema-path`` finds it through
the installed package for jsonschema2md to render, and the page it renders is
then titled for this site and given the key map from the filename transform,
so the page can't drift from the code.
"""

import json
import sys
from argparse import ArgumentParser
from importlib.metadata import version
from importlib.resources import files
from pathlib import Path
from typing import Final

from comicbox.formats.filename.transform import SIMPLE_KEY_MAP

PACKAGE: Final = "comicfn2dict"
SCHEMA_PATH: Final = Path(str(files(PACKAGE) / "schemas" / f"{PACKAGE}.schema.json"))
# jsonschema2md titles the page with the schema's title, the package name.
GENERATED_TITLE: Final = f"# {PACKAGE}"
TITLE: Final = "# Filename"
NOTE_HEADING: Final = "## Keys comicbox keeps"


def _source_line(schema: dict) -> str:
    """Cite the schema file and the package version it came from."""
    return (
        f"Generated from [{SCHEMA_PATH.name}]({schema['$id']}) in {PACKAGE}"
        f" {version(PACKAGE)}."
    )


def _keys_note(schema: dict) -> str:
    """List the keys comicbox maps to its own fields, and the ones it drops."""
    properties = schema["properties"]
    readable = {key for key, prop in properties.items() if not prop.get("writeOnly")}
    dropped = sorted(readable - SIMPLE_KEY_MAP.keys())
    dropped_list = (
        ", ".join(f"`{key}`" for key in dropped[:-1]) + f" and `{dropped[-1]}`"
    )
    lines = [
        NOTE_HEADING,
        "",
        "Comicbox reads these keys from a filename into its own fields, and writes",
        f"them back. It drops {dropped_list}.",
        "",
        f"| {PACKAGE} key | comicbox field |",
        "| --- | --- |",
    ]
    lines += [
        f"| `{key}` | `{keypath}` |" for key, keypath in sorted(SIMPLE_KEY_MAP.items())
    ]
    return "\n".join(lines) + "\n"


def finish(page: Path) -> None:
    """Title the rendered page, cite its source and append the keys note."""
    schema = json.loads(SCHEMA_PATH.read_text())
    title, body = page.read_text().split("\n", 1)
    if title != GENERATED_TITLE:
        msg = f"{page}: expected {GENERATED_TITLE!r} as the title, got {title!r}"
        raise ValueError(msg)
    page.write_text(
        "\n".join(
            (TITLE, "", _source_line(schema), body.rstrip(), "", _keys_note(schema))
        )
    )


def main() -> None:
    """Print the schema's path, or finish the page rendered from it."""
    parser = ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--schema-path", action="store_true", help="print the packaged schema's path"
    )
    group.add_argument("page", nargs="?", type=Path, help="the rendered page to finish")
    args = parser.parse_args()
    if args.schema_path:
        sys.stdout.write(f"{SCHEMA_PATH}\n")
    else:
        finish(args.page)


if __name__ == "__main__":
    main()
