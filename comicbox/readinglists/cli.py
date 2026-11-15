"""
``comicbox readinglist``, or ``comicbox rl``: work with reading lists.

Its own parser with real subcommands, not the main parser: that parser's
positionals are always comic archives and its option dests are tested
against the config template. Exits 0 on success, 1 when a reading-list
error stops it or any file fails, and 2 for a usage error.
"""

import re
from argparse import ArgumentParser, Namespace
from collections.abc import Callable, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING

from comicbox.exceptions import ReadingListError
from comicbox.readinglists.arcs import reading_lists_from_comics
from comicbox.readinglists.combine import combine
from comicbox.readinglists.compare import compare
from comicbox.readinglists.registry import (
    ReadingListFormats,
    as_text,
    detect_format,
    get_format,
)
from comicbox.readinglists.render import (
    console,
    print_combine_report,
    print_comparison,
    print_error,
    print_messages,
    print_reading_list,
    print_status,
)
from comicbox.readinglists.schema import ENTRIES_KEY, NAME_KEY
from comicbox.readinglists.serialize import (
    ReadingListResult,
    dumps,
    load,
    loads,
    lost_fields,
)

if TYPE_CHECKING:
    from rich.console import Console

PROG = "comicbox readinglist"
_DEFAULT_FORMAT = ReadingListFormats.YAML
_FORMAT_TOKENS = tuple(
    sorted(token for fmt in ReadingListFormats for token in fmt.value.tokens)
)
# -Q counts, as in a comicbox run.
_QUIET_LOGLEVELS = MappingProxyType({1: "WARNING", 2: "ERROR"})
_UNSAFE_FILENAME_RE = re.compile(r'[\x00-\x1f/\\:*?"<>|]+')

_DESCRIPTION = """Read, convert, combine and compare reading lists.

Formats: ComicRack .cbl, json-cbl, and comicbox's own YAML and JSON.
`comicbox rl` is the short form. A comic file named readinglist or rl has
to be given to comicbox as ./readinglist or ./rl."""


class _Run:
    """One command: its arguments, its consoles and whether anything failed."""

    def __init__(self, args: Namespace) -> None:
        self.args = args
        self.out: Console = console()
        self.err: Console = console(stderr=True)
        self.failed = False

    def load(self, path: Path) -> ReadingListResult | None:
        """Read a list, or report why not and carry on."""
        try:
            return load(path)
        except (OSError, ReadingListError) as exc:
            print_error(self.err, path, exc)
            self.failed = True
            return None

    def write(
        self, reading_list: dict, fmt: ReadingListFormats, path: Path | None
    ) -> None:
        """Write a list to a file, or to stdout, after naming its losses."""
        print_messages(self.err, lost_fields(reading_list, fmt), "lost")
        text = dumps(reading_list, fmt)
        if path is None:
            self.out.out(text, end="" if text.endswith("\n") else "\n")
            return
        path.write_text(text.rstrip("\n") + "\n")
        print_status(self.err, path, ok=True, detail=f"written as {fmt.value.label}")

    @property
    def exit_code(self) -> int:
        """1 when any file failed."""
        return int(self.failed)


def _print(run: _Run) -> None:
    for path in run.args.files:
        if result := run.load(path):
            print_reading_list(run.out, path, result)


def _validate_one(run: _Run, path: Path) -> None:
    """Check a file against its format's schema, if any, then read it."""
    from comicbox.validate.spec import build_validator, validation_failure_exceptions

    text = as_text(path.read_bytes())
    fmt = detect_format(text)
    if fmt is None:
        print_status(run.out, path, ok=False, detail="not a reading list")
        run.failed = True
        return
    if spec := fmt.value.validator_spec:
        try:
            build_validator(spec).validate(text)
        except validation_failure_exceptions() as exc:
            print_status(run.out, path, ok=False, detail=f"{fmt.value.label}: {exc}")
            run.failed = True
            return
    result = loads(text, fmt=fmt)
    entries = result.reading_list.get(ENTRIES_KEY) or ()
    detail = f"{fmt.value.label}, {len(entries)} entries"
    print_status(run.out, path, ok=True, detail=detail)
    print_messages(run.out, result.warnings, "warning")


def _validate(run: _Run) -> None:
    for path in run.args.files:
        try:
            _validate_one(run, path)
        except (OSError, ReadingListError) as exc:
            print_status(run.out, path, ok=False, detail=str(exc))
            run.failed = True


def _output_path(source: Path, fmt: ReadingListFormats, directory: Path | None) -> Path:
    return (directory or source.parent) / (source.stem + fmt.value.suffix)


def _convert(run: _Run) -> None:
    fmt = get_format(run.args.to)
    for path in run.args.files:
        if not (result := run.load(path)):
            continue
        destination = _output_path(path, fmt, run.args.output)
        if destination.resolve() == path.resolve():
            reason = "converting would overwrite the input; give -o DIR"
            print_error(run.err, path, ReadingListError(reason))
            run.failed = True
            continue
        run.write(result.reading_list, fmt, destination)


def _combine(run: _Run) -> None:
    paths = [run.args.primary, *run.args.others]
    results = [run.load(path) for path in paths]
    if run.failed:
        return
    result = combine([result.reading_list for result in results if result])
    run.write(result.reading_list, get_format(run.args.to), run.args.output)
    print_combine_report(run.err, result, paths)


def _compare(run: _Run) -> None:
    if (a := run.load(run.args.a)) and (b := run.load(run.args.b)):
        print_comparison(run.out, compare(a.reading_list, b.reading_list))


def _read_comics(run: _Run, directory: Path) -> list[dict]:
    """Read every comic's tags under a directory, in path order."""
    from comicbox.config import get_config
    from comicbox.process import iter_process_files
    from comicbox.run import iter_recurse

    config = get_config(Namespace(comicbox=Namespace()))
    tags: dict[Path, dict] = {}
    for path, (result, error) in iter_process_files(iter_recurse(directory), config):
        if error is not None:
            print_error(run.err, path, error)
            run.failed = True
        elif result["tags"]:
            tags[path] = result["tags"]
    return [tags[path] for path in sorted(tags)]


def _list_filename(name: str, taken: set[str]) -> str:
    stem = _UNSAFE_FILENAME_RE.sub("_", name).strip(" .") or "reading-list"
    candidate, number = stem, 1
    while candidate.casefold() in taken:
        number += 1
        candidate = f"{stem} {number}"
    taken.add(candidate.casefold())
    return candidate


def _from_arcs(run: _Run) -> None:
    directory: Path = run.args.directory
    if not directory.is_dir():
        print_error(run.err, directory, ReadingListError("not a directory"))
        run.failed = True
        return
    fmt = get_format(run.args.to)
    output: Path = run.args.output or Path()
    output.mkdir(parents=True, exist_ok=True)
    taken: set[str] = set()
    for reading_list in reading_lists_from_comics(_read_comics(run, directory)):
        filename = _list_filename(reading_list.get(NAME_KEY) or "", taken)
        run.write(reading_list, fmt, output / (filename + fmt.value.suffix))


_ACTIONS: MappingProxyType[str, Callable[[_Run], None]] = MappingProxyType(
    {
        "print": _print,
        "validate": _validate,
        "convert": _convert,
        "combine": _combine,
        "compare": _compare,
        "from-arcs": _from_arcs,
    }
)


def _add_format_option(parser: ArgumentParser, help_text: str) -> None:
    parser.add_argument(
        "--to",
        choices=_FORMAT_TOKENS,
        default=_DEFAULT_FORMAT.name.lower(),
        metavar="FMT",
        help=f"{help_text} One of: {', '.join(_FORMAT_TOKENS)}.",
    )


def build_parser() -> ArgumentParser:
    """Build the ``comicbox readinglist`` parser."""
    parser = ArgumentParser(prog=PROG, description=_DESCRIPTION)
    parser.add_argument(
        "-Q",
        "--quiet",
        action="count",
        default=0,
        help="Log less, as in a comicbox run.",
    )
    actions = parser.add_subparsers(dest="action", required=True, metavar="ACTION")
    sub = actions.add_parser("print", help="Print each list as a table.")
    sub.add_argument("files", nargs="+", type=Path, metavar="FILE")
    sub = actions.add_parser("validate", help="Check each file against its format.")
    sub.add_argument("files", nargs="+", type=Path, metavar="FILE")
    sub = actions.add_parser("convert", help="Write each list in another format.")
    _add_format_option(sub, "The format to write.")
    sub.add_argument(
        "-o",
        "--output",
        type=Path,
        metavar="DIR",
        help="Write here, not beside each input.",
    )
    sub.add_argument("files", nargs="+", type=Path, metavar="FILE")
    sub = actions.add_parser(
        "combine", help="Combine lists of one reading order, primary first."
    )
    _add_format_option(sub, "The format to write.")
    sub.add_argument(
        "-o", "--output", type=Path, metavar="FILE", help="Write here, not to stdout."
    )
    sub.add_argument("primary", type=Path, metavar="PRIMARY")
    sub.add_argument("others", nargs="+", type=Path, metavar="OTHER")
    sub = actions.add_parser("compare", help="Say whether two lists are the same list.")
    sub.add_argument("a", type=Path, metavar="A")
    sub.add_argument("b", type=Path, metavar="B")
    sub = actions.add_parser(
        "from-arcs",
        help="Write one list per story arc the comics in DIR are tagged with.",
    )
    _add_format_option(sub, "The format to write.")
    sub.add_argument(
        "-o",
        "--output",
        type=Path,
        metavar="DIR",
        help="Write here, not the current directory.",
    )
    sub.add_argument("directory", type=Path, metavar="DIR")
    return parser


def main(params: Sequence[str]) -> int:
    """Run ``comicbox readinglist`` on the args after it; return the exit code."""
    from comicbox.logger import init_logging

    args = build_parser().parse_args(params)
    init_logging(_QUIET_LOGLEVELS.get(args.quiet, "CRITICAL") if args.quiet else "INFO")
    run = _Run(args)
    try:
        _ACTIONS[args.action](run)
    except ReadingListError as exc:
        print_error(run.err, None, exc)
        return 1
    return run.exit_code
