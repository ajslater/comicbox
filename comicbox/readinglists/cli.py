"""
``comicbox readinglist``, or ``comicbox rl``: work with reading lists.

Its own parser with real subcommands, not the main parser: that parser's
positionals are always comic archives and its option dests are tested
against the config template. Exits 0 on success, 1 when a reading-list or
file error stops it or any file fails, and 2 for a usage error.

stdout carries only what was asked for, a list or a table; warnings,
losses, reports and log lines go to stderr. Nothing is written over an
input, and nothing over an existing file without ``--overwrite``.
"""

import os
import re
from argparse import ArgumentParser, Namespace
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from comicbox.exceptions import ReadingListError
from comicbox.readinglists.arcs import reading_lists_from_comics
from comicbox.readinglists.combine import combine
from comicbox.readinglists.compare import compare
from comicbox.readinglists.identity import entry_keys
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


def _same_file_key(path: Path) -> str:
    """Compare paths as a case-insensitive filesystem would."""
    return str(path.resolve()).casefold()


def write_text(path: Path, text: str) -> None:
    """Write a UTF-8 file whole, or leave whatever was there."""
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temp.write_text(text, encoding="utf-8")
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


@dataclass(frozen=True, slots=True)
class _Destinations:
    """Where a command will write, and what it must not write over."""

    counts: Counter[str]
    inputs: frozenset[str]
    overwrite: bool
    make_parents: bool

    def problem(self, destination: Path, key: str) -> str | None:
        """Say why one destination cannot be written, or None."""
        if key in self.inputs:
            return "is one of the inputs"
        if self.counts[key] > 1:
            return f"would be written by {self.counts[key]} inputs"
        if destination.exists() and not self.overwrite:
            return "exists; --overwrite replaces it"
        if not self.make_parents and not destination.parent.is_dir():
            return "its directory does not exist"
        return None


def destination_problems(
    destinations: Sequence[Path],
    inputs: Sequence[Path],
    *,
    overwrite: bool,
    make_parents: bool = False,
) -> list[tuple[Path, str]]:
    """Name each destination that is an input, shared, taken or unreachable."""
    checks = _Destinations(
        Counter(_same_file_key(path) for path in destinations),
        frozenset(_same_file_key(path) for path in inputs),
        overwrite,
        make_parents,
    )
    problems: list[tuple[Path, str]] = []
    reported: set[str] = set()
    for destination in destinations:
        key = _same_file_key(destination)
        if key not in reported and (reason := checks.problem(destination, key)):
            problems.append((destination, reason))
            reported.add(key)
    return problems


def _no_key_count(reading_list: Mapping[str, Any]) -> int:
    return sum(not entry_keys(entry) for entry in reading_list.get(ENTRIES_KEY) or ())


class _Run:
    """One command: its arguments, its consoles and whether anything failed."""

    def __init__(self, args: Namespace) -> None:
        self.args = args
        self.out: Console = console()
        self.err: Console = console(stderr=True)
        self.failed = False

    def fail(self, path: Path | None, error: BaseException) -> None:
        """Report one failure on stderr and carry on."""
        print_error(self.err, path, error)
        self.failed = True

    def load(self, path: Path) -> ReadingListResult | None:
        """Read a list and report what the read dropped, or why it failed."""
        try:
            result = load(path)
        except (OSError, ReadingListError) as exc:
            self.fail(path, exc)
            return None
        print_messages(self.err, result.warnings, f"{path}: warning")
        return result

    def refuse(self, problems: Sequence[tuple[Path, str]]) -> bool:
        """Report every destination problem; whether there were any."""
        for destination, reason in problems:
            self.fail(destination, ReadingListError(reason))
        return bool(problems)

    def write(
        self, reading_list: dict, fmt: ReadingListFormats, path: Path | None
    ) -> None:
        """Write a list to a file, or to stdout, after naming its losses."""
        print_messages(self.err, lost_fields(reading_list, fmt), "lost")
        text = dumps(reading_list, fmt)
        if path is None:
            self.out.out(text, end="" if text.endswith("\n") else "\n")
            return
        try:
            write_text(path, text.rstrip("\n") + "\n")
        except OSError as exc:
            self.fail(path, exc)
            return
        print_status(self.err, path, ok=True, detail=f"written as {fmt.value.label}")

    def no_keys(self, paths: Sequence[Path], lists: Sequence[Mapping]) -> None:
        """Say how many entries of each input can match nothing."""
        for path, reading_list in zip(paths, lists, strict=True):
            if count := _no_key_count(reading_list):
                what = (
                    "entry has no key and matches"
                    if count == 1
                    else "entries have no key and match"
                )
                message = f"{path}: {count} {what} nothing"
                print_messages(self.err, (message,), "warning")

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
    if (fmt := detect_format(text)) is None:
        result = loads(text)  # Raises with the reason: syntax, or no list.
        fmt = result.fmt
    if spec := fmt.value.validator_spec:
        try:
            build_validator(spec).validate(text)
        except validation_failure_exceptions() as exc:
            message = " ".join(str(exc).split("\n", 1)[0].split())
            print_status(
                run.out, path, ok=False, detail=f"{fmt.value.label}: {message}"
            )
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
    plan = [(path, _output_path(path, fmt, run.args.output)) for path in run.args.files]
    destinations = [destination for _, destination in plan]
    if run.refuse(
        destination_problems(
            destinations,
            run.args.files,
            overwrite=run.args.overwrite,
            make_parents=run.args.output is not None,
        )
    ):
        return
    if run.args.output:
        run.args.output.mkdir(parents=True, exist_ok=True)
    for path, destination in plan:
        if result := run.load(path):
            run.write(result.reading_list, fmt, destination)


def _combine(run: _Run) -> None:
    paths = [run.args.primary, *run.args.others]
    if run.args.output and run.refuse(
        destination_problems([run.args.output], paths, overwrite=run.args.overwrite)
    ):
        return
    results = [run.load(path) for path in paths]
    if run.failed:
        return
    lists = [result.reading_list for result in results if result]
    result = combine(lists)
    run.write(result.reading_list, get_format(run.args.to), run.args.output)
    print_combine_report(run.err, result, paths)
    run.no_keys(paths, lists)


def _compare(run: _Run) -> None:
    if (a := run.load(run.args.a)) and (b := run.load(run.args.b)):
        print_comparison(run.out, compare(a.reading_list, b.reading_list))
        run.no_keys((run.args.a, run.args.b), (a.reading_list, b.reading_list))


def _read_comics(run: _Run, directory: Path) -> list[dict]:
    """Read every comic's tags under a directory, in path order."""
    from comicbox.config import get_config
    from comicbox.process import iter_process_files
    from comicbox.run import iter_recurse

    config = get_config(Namespace(comicbox=Namespace()))
    tags: dict[Path, dict] = {}
    for path, (result, error) in iter_process_files(iter_recurse(directory), config):
        if error is not None:
            run.fail(path, error)
        elif result["tags"]:
            tags[path] = result["tags"]
    return [tags[path] for path in sorted(tags)]


def _list_filename(name: str, taken: set[str]) -> str:
    """Name a list's file after it, never twice in one directory."""
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
        run.fail(directory, ReadingListError("not a directory"))
        return
    fmt = get_format(run.args.to)
    output: Path = run.args.output or Path()
    taken: set[str] = set()
    plan = [
        (
            reading_list,
            output
            / (
                _list_filename(reading_list.get(NAME_KEY) or "", taken)
                + fmt.value.suffix
            ),
        )
        for reading_list in reading_lists_from_comics(_read_comics(run, directory))
    ]
    destinations = [destination for _, destination in plan]
    if run.refuse(
        destination_problems(
            destinations, (), overwrite=run.args.overwrite, make_parents=True
        )
    ):
        return
    output.mkdir(parents=True, exist_ok=True)
    for reading_list, destination in plan:
        run.write(reading_list, fmt, destination)


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


def _add_write_options(parser: ArgumentParser, output: str, help_text: str) -> None:
    parser.add_argument(
        "--to",
        choices=_FORMAT_TOKENS,
        default=_DEFAULT_FORMAT.name.lower(),
        metavar="FMT",
        help=f"The format to write, yaml by default. One of: {', '.join(_FORMAT_TOKENS)}.",
    )
    parser.add_argument("-o", "--output", type=Path, metavar=output, help=help_text)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace files that exist. An input is never written over.",
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
    _add_write_options(sub, "DIR", "Write here, not beside each input.")
    sub.add_argument("files", nargs="+", type=Path, metavar="FILE")
    sub = actions.add_parser(
        "combine", help="Combine lists of one reading order, primary first."
    )
    _add_write_options(sub, "FILE", "Write here, not to stdout.")
    sub.add_argument("primary", type=Path, metavar="PRIMARY")
    sub.add_argument("others", nargs="+", type=Path, metavar="OTHER")
    sub = actions.add_parser("compare", help="Say whether two lists are the same list.")
    sub.add_argument("a", type=Path, metavar="A")
    sub.add_argument("b", type=Path, metavar="B")
    sub = actions.add_parser(
        "from-arcs",
        help="Write one list per story arc the comics in DIR are tagged with.",
    )
    _add_write_options(sub, "DIR", "Write here, not the current directory.")
    sub.add_argument("directory", type=Path, metavar="DIR")
    return parser


def main(params: Sequence[str]) -> int:
    """Run ``comicbox readinglist`` on the args after it; return the exit code."""
    from comicbox.logger import init_logging

    args = build_parser().parse_args(params)
    level = _QUIET_LOGLEVELS.get(args.quiet, "CRITICAL") if args.quiet else "INFO"
    init_logging(level, sink="stderr")
    run = _Run(args)
    try:
        _ACTIONS[args.action](run)
    except (OSError, ReadingListError) as exc:
        run.fail(None, exc)
        return 1
    return run.exit_code
