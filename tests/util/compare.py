"""File/string comparison helpers that ignore volatile metadata fields."""

import re
from pathlib import Path

from ruamel.yaml import YAML

from comicbox.box.validate import validate_source
from comicbox.formats.comic_book_info.schema import (
    LAST_MODIFIED_TAG as CBI_LAST_MODIFIED_TAG,
)
from comicbox.formats.comicbox.schema import (
    NOTES_KEY,
    UPDATED_AT_KEY,
    ComicboxSchemaMixin,
)
from comicbox.formats.metron_info.schema import (
    LAST_MODIFIED_TAG as METRON_LAST_MODIFIED_TAG,
)

from .diff import assert_diff

_NOTES_TAGS = ("notes:", r'"notes":', "<Notes>", "<pdf:Producer>", "&lt;Notes&gt;")
_LAST_MODIFIED_TAGS = (rf'"{CBI_LAST_MODIFIED_TAG}":', rf"<{METRON_LAST_MODIFIED_TAG}>")
_MOD_DATE_TAGS = ('"modDate":', "<pdf:ModDate>")
# NB: key-colon order matters — JSON renders '"page_count":', not
# '"page_count:"'. The old misquoted patterns could never match, so these
# ignore flags silently compared nothing; the pages/<identifier> lines were
# instead pruned unconditionally by a "temporary" always-on list.
_PAGE_COUNT_TAGS = ('"page_count":', "page_count:", "<pages>", "pages:", '"pages":')
_IDENTIFIERS_TAGS = ('"identifiers":', "identifiers:", "<identifier>")
_TAGGER_TAGS = ('"appID":',)


def _prune_lines(
    lines: list[str],
    *,
    ignore_last_modified: bool,
    ignore_notes: bool,
    ignore_updated_at: bool,
    ignore_mod_date: bool,
    ignore_page_count: bool,
    ignore_identifiers: bool,
    ignore_tagger: bool,
) -> list[str]:
    flagged_tags = (
        (ignore_updated_at, (UPDATED_AT_KEY,)),
        (ignore_mod_date, _MOD_DATE_TAGS),
        (ignore_last_modified, _LAST_MODIFIED_TAGS),
        (ignore_notes, _NOTES_TAGS),
        (ignore_page_count, _PAGE_COUNT_TAGS),
        (ignore_identifiers, _IDENTIFIERS_TAGS),
        (ignore_tagger, _TAGGER_TAGS),
    )
    skip_substrings = [tag for flag, tags in flagged_tags if flag for tag in tags]
    if not skip_substrings:
        # An empty alternation would match (and prune) every line.
        return lines
    skipped_line_re = re.compile("|".join(re.escape(s) for s in skip_substrings))
    return [line for line in lines if not skipped_line_re.search(line)]


def _prune_same_lines(  # noqa: PLR0913
    a_lines: list[str],
    b_lines: list[str],
    *,
    ignore_last_modified: bool,
    ignore_notes: bool,
    ignore_updated_at: bool,
    ignore_mod_date: bool,
    ignore_page_count: bool,
    ignore_identifiers: bool,
    ignore_tagger: bool,
) -> tuple[list[str], list[str]]:
    a_lines = _prune_lines(
        a_lines,
        ignore_last_modified=ignore_last_modified,
        ignore_notes=ignore_notes,
        ignore_updated_at=ignore_updated_at,
        ignore_mod_date=ignore_mod_date,
        ignore_page_count=ignore_page_count,
        ignore_identifiers=ignore_identifiers,
        ignore_tagger=ignore_tagger,
    )
    b_lines = _prune_lines(
        b_lines,
        ignore_last_modified=ignore_last_modified,
        ignore_notes=ignore_notes,
        ignore_updated_at=ignore_updated_at,
        ignore_mod_date=ignore_mod_date,
        ignore_page_count=ignore_page_count,
        ignore_identifiers=ignore_identifiers,
        ignore_tagger=ignore_tagger,
    )
    return a_lines, b_lines


def prune_strings(
    a_str: str,
    b_str: str,
    *,
    ignore_last_modified: bool,
    ignore_notes: bool,
    ignore_updated_at: bool,
    ignore_mod_date: bool,
) -> tuple[str, str]:
    a_lines = a_str.splitlines()
    b_lines = b_str.splitlines()
    a_lines, b_lines = _prune_same_lines(
        a_lines,
        b_lines,
        ignore_last_modified=ignore_last_modified,
        ignore_notes=ignore_notes,
        ignore_updated_at=ignore_updated_at,
        ignore_mod_date=ignore_mod_date,
        ignore_page_count=False,
        ignore_identifiers=False,
        ignore_tagger=False,
    )
    a_str = "\n".join(a_lines)
    b_str = "\n".join(b_lines)
    return a_str, b_str


def compare_files(  # noqa: PLR0913
    path_a: Path,
    path_b: Path,
    *,
    ignore_last_modified: bool,
    ignore_notes: bool,
    ignore_updated_at: bool,
    ignore_mod_date: bool,
    ignore_page_count: bool,
    ignore_identifiers: bool,
    ignore_tagger: bool,
) -> bool:
    """Compare file contents."""
    with path_a.open("r") as file_a, path_b.open("r") as file_b:
        a_lines = file_a.readlines()
        b_lines = file_b.readlines()

    a_lines, b_lines = _prune_same_lines(
        a_lines,
        b_lines,
        ignore_last_modified=ignore_last_modified,
        ignore_notes=ignore_notes,
        ignore_updated_at=ignore_updated_at,
        ignore_mod_date=ignore_mod_date,
        ignore_page_count=ignore_page_count,
        ignore_identifiers=ignore_identifiers,
        ignore_tagger=ignore_tagger,
    )

    if len(a_lines) != len(b_lines):
        # Strict length check: zip(strict=False) silently passed
        # truncated output.
        print(  # noqa: T201
            f"line count differs: {path_a}={len(a_lines)} {path_b}={len(b_lines)}"
        )
        print("".join(b_lines))  # noqa: T201
        return False
    for line_a, line_b in zip(a_lines, b_lines, strict=True):
        if line_a != line_b:
            print(f"{path_a}: {line_a}")  # noqa: T201
            print(f"{path_b}: {line_b}")  # noqa: T201
            print("".join(b_lines))  # noqa: T201
            return False
    return True


def load_cli_and_compare_dicts(
    path_a: Path,
    path_b: Path,
    *,
    ignore_updated_at: bool = True,
    ignore_notes: bool = True,
) -> None:
    """Compare cli strings all on one line."""
    yaml = YAML()
    with path_a.open("r") as file_a, path_b.open("r") as file_b:
        dict_a = yaml.load(file_a)
        dict_b = yaml.load(file_b)
    if ignore_updated_at:
        dict_a[ComicboxSchemaMixin.ROOT_TAG].pop(UPDATED_AT_KEY, None)
        dict_b[ComicboxSchemaMixin.ROOT_TAG].pop(UPDATED_AT_KEY, None)
    if ignore_notes:
        dict_a[ComicboxSchemaMixin.ROOT_TAG].pop(NOTES_KEY, None)
        dict_b[ComicboxSchemaMixin.ROOT_TAG].pop(NOTES_KEY, None)

    assert_diff(dict_a, dict_b)


def compare_export(
    test_dir: Path, fn: Path, test_fn: str | None = None, *, validate: bool = True
) -> None:
    """Compare exported files."""
    if validate:
        validate_source(fn)
    if test_fn is None:
        test_fn = fn.name.lower()
    test_path = test_dir / test_fn
    if fn.name == "comicbox-cli.yaml":
        load_cli_and_compare_dicts(test_path, fn)
    else:
        assert compare_files(
            test_path,
            fn,
            ignore_last_modified=True,
            ignore_notes=True,
            ignore_updated_at=True,
            ignore_mod_date=True,
            ignore_page_count=True,
            ignore_identifiers=True,
            ignore_tagger=True,
        )
