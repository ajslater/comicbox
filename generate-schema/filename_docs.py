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

from comicbox.formats.filename.transform import READ_ONLY_KEY_MAP, SIMPLE_KEY_MAP

PACKAGE: Final = "comicfn2dict"
SCHEMA_PATH: Final = Path(str(files(PACKAGE) / "schemas" / f"{PACKAGE}.schema.json"))
# jsonschema2md titles the page with the schema's title, the package name.
GENERATED_TITLE: Final = f"# {PACKAGE}"
TITLE: Final = "# Filename"
NOTE_HEADING: Final = "## Keys comicbox keeps"
# comicfn2dict's EBNF grammar for these names, on its own docs site.
GRAMMAR_URL: Final = "https://comicfn2dict.readthedocs.io/FILENAMES/"


def _source_line(schema: dict) -> str:
    """Cite the schema file and version, and point at the grammar it pairs with."""
    return (
        f"Generated from [{SCHEMA_PATH.name}]({schema['$id']}) in {PACKAGE}"
        f" {version(PACKAGE)}. See also [Filename Format ↗]({GRAMMAR_URL}), the"
        f" grammar of these names, on {PACKAGE}'s own docs site."
    )


def _listed(keys: list[str]) -> str:
    """Join keys as code spans the way a sentence lists them: a, b and c."""
    spans = [f"`{key}`" for key in keys]
    return " and ".join(filter(None, (", ".join(spans[:-1]), spans[-1])))


def _keys_note(schema: dict) -> str:
    """Tabulate the keys comicbox maps to its own fields, and note the rest."""
    properties = schema["properties"]
    readable = {key for key, prop in properties.items() if not prop.get("writeOnly")}
    lines = [
        NOTE_HEADING,
        "",
        "Comicbox reads these keys from a filename into its own fields, and writes",
        "them back.",
        "",
        f"| {PACKAGE} key | comicbox field |",
        "| --- | --- |",
        *(
            f"| `{key}` | `{keypath}` |"
            for key, keypath in sorted(SIMPLE_KEY_MAP.items())
        ),
    ]
    notes = [
        f"It reads `{key}` into `{keypath}` but never writes it into a filename."
        for key, keypath in sorted(READ_ONLY_KEY_MAP.items())
    ]
    if dropped := sorted(readable - SIMPLE_KEY_MAP.keys() - READ_ONLY_KEY_MAP.keys()):
        notes.append(f"It drops {_listed(dropped)}.")
    if notes:
        lines += ["", " ".join(notes)]
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
