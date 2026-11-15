"""
``comicbox readinglist``, or ``comicbox rl``: work with reading lists.

Its own parser with real subcommands, not the main parser: that parser's
positionals are always comic archives and its option dests are tested
against the config template. Exits 0 on success, 1 when a reading-list,
file or network error stops it or any file fails, 2 for a usage error and
130 when a fetch is cancelled with Ctrl-C.

stdout carries only what was asked for, a list or a table; warnings,
losses, reports and log lines go to stderr. Nothing is written over an
input, and nothing over an existing file without ``--overwrite``.
"""

import os
import re
import sys
import threading
from argparse import ArgumentParser, ArgumentTypeError, Namespace
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, TypeVar
from urllib.parse import urlsplit

from confuse import ConfigError
from rich_argparse import RichHelpFormatter

from comicbox.cli.parser import add_online_auth_group, add_online_cache_group
from comicbox.events import (
    Event,
    ReadingListFetchProgress,
    ReadingListFetchStarted,
)
from comicbox.exceptions import (
    ConfigurationError,
    OnlineLookupAbortedError,
    ReadingListError,
)
from comicbox.readinglists.arcs import reading_lists_from_comics
from comicbox.readinglists.combine import combine
from comicbox.readinglists.compare import compare
from comicbox.readinglists.identity import entry_keys
from comicbox.readinglists.registry import (
    ReadingListFormats,
    as_text,
    get_format,
)
from comicbox.readinglists.render import (
    console,
    print_catalog_entries,
    print_combine_report,
    print_comparison,
    print_error,
    print_messages,
    print_metron_lists,
    print_note,
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
    readable_depth,
    resolve_format,
)
from comicbox.readinglists.session import ReadingListSession

if sys.version_info >= (3, 12):
    from typing import override  # pyright: ignore[reportUnreachable]
else:
    from typing_extensions import override

if TYPE_CHECKING:
    from rich.console import Console

    from comicbox.config.settings import ComicboxSettings

_T = TypeVar("_T")

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
    except OSError as exc:
        if exc.filename is not None:
            # Name the destination, not the temporary file beside it.
            exc.filename = str(path)
        raise
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
        if destination.is_dir():
            return "is a directory"
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
        # Set by the user's Ctrl-C, so a spent quota is not taken for one.
        self.cancelled = False

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

    data = path.read_bytes()
    text = as_text(data)
    fmt = resolve_format(text)  # Raises with the reason: syntax, or no list.
    if spec := fmt.value.validator_spec:
        # The validator's message pretty-prints the value it rejects, which
        # recurses as deeply as the value nests.
        with readable_depth():
            try:
                build_validator(spec).validate(text)
            except validation_failure_exceptions() as exc:
                message = " ".join(str(exc).split("\n", 1)[0].split())
                print_status(
                    run.out, path, ok=False, detail=f"{fmt.value.label}: {message}"
                )
                run.failed = True
                return
    result = loads(data, fmt=fmt)
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


# Online actions.

# The parsed dests that are settings. No other dest may reach the config.
_SETTING_DESTS = ("auth", "cache", "cache_dir", "cache_ttl", "general.config")
_URL_SCHEMES = frozenset({"http", "https"})
_URL_KIND = "url"
_METRON_KINDS = frozenset({"metron", "metron-arc"})
_CATALOG_KIND = "catalog"
_SEARCH_WHERE = ("metron", _CATALOG_KIND)
_JOIN_POLL_SECONDS = 0.1
EXIT_CANCELLED = 130


@dataclass(frozen=True, slots=True)
class FetchSpec:
    """What ``fetch`` was asked for: a source kind and its id, path or URL."""

    kind: str
    target: str

    @override
    def __str__(self) -> str:
        """Spell it as it was given."""
        return self.target if self.kind == _URL_KIND else f"{self.kind}:{self.target}"


def fetch_spec(text: str) -> FetchSpec:
    """Parse ``metron:ID``, ``metron-arc:ID``, ``catalog:PATH`` or a URL."""
    if urlsplit(text).scheme.lower() in _URL_SCHEMES:
        return FetchSpec(_URL_KIND, text)
    kind, colon, target = text.partition(":")
    kind = kind.lower()
    # ASCII digits only: "²" is a digit to isdigit and not to int.
    if colon and kind in _METRON_KINDS and target.isascii() and target.isdigit():
        return FetchSpec(kind, target)
    if colon and kind == _CATALOG_KIND and target.strip():
        return FetchSpec(kind, target)
    reason = f"{text!r}: give metron:ID, metron-arc:ID, catalog:PATH or an http(s) URL"
    raise ArgumentTypeError(reason)


_Fetcher = Callable[[ReadingListSession, str], ReadingListResult | None]
_FETCHERS: MappingProxyType[str, _Fetcher] = MappingProxyType(
    {
        "metron": lambda session, target: session.fetch_metron_list(int(target)),
        "metron-arc": lambda session, target: session.fetch_metron_arc(int(target)),
        _CATALOG_KIND: lambda session, target: session.fetch_catalog(target),
        _URL_KIND: lambda session, target: session.fetch_url(target),
    }
)


def _settings(args: Namespace) -> "ComicboxSettings":
    """Build settings from the setting dests alone, as the doctor does."""
    from comicbox.config import get_config

    dests = {dest: getattr(args, dest, None) for dest in _SETTING_DESTS}
    return get_config(Namespace(comicbox=Namespace(**dests)))


class _Progress:
    """Say on stderr what a fetch is doing, unless told to be quiet."""

    def __init__(self, err: "Console", *, quiet: bool) -> None:
        self._err = err
        self._quiet = quiet

    def __call__(self, event: Event) -> None:
        """Print a fetch's start and each part that arrives."""
        if self._quiet:
            return
        if isinstance(event, ReadingListFetchStarted):
            print_note(self._err, f"Fetching {event.source} {event.key}...")
        elif isinstance(event, ReadingListFetchProgress) and event.index is not None:
            total = f" of {event.total:,}" if event.total is not None else ""
            print_note(self._err, f"  {event.index:,}{total} entries")


def open_session(run: _Run) -> ReadingListSession:
    """Open a session on the command's settings, reporting progress."""
    from comicbox.version import set_user_agent_context

    set_user_agent_context("cli", client="readinglist")
    progress = _Progress(run.err, quiet=run.args.quiet > 0)
    return ReadingListSession(config=_settings(run.args), on_event=progress)


def _cancellable(run: _Run, session: ReadingListSession, call: Callable[[], _T]) -> _T:
    """
    Run ``call`` on a worker so the first Ctrl-C cancels it cleanly.

    The cancel stops the fetch before its next request, which can wait out
    one rate-limit window. A second Ctrl-C quits at once.
    """
    outcome: list[Any] = []

    def work() -> None:
        try:
            outcome.append((True, call()))
        except BaseException as exc:
            outcome.append((False, exc))

    worker = threading.Thread(target=work, name="readinglist-fetch", daemon=True)
    worker.start()
    try:
        while worker.is_alive():
            worker.join(_JOIN_POLL_SECONDS)
    except KeyboardInterrupt:
        run.cancelled = True
        session.cancel()
        print_note(
            run.err, "Cancelling before the next request; Ctrl-C again quits now."
        )
        while worker.is_alive():
            worker.join(_JOIN_POLL_SECONDS)
    ok, value = outcome[0]
    if not ok:
        raise value
    return value


def _fetch(run: _Run) -> None:
    spec: FetchSpec = run.args.spec
    fmt = get_format(run.args.to)
    output: Path | None = run.args.output
    if output and run.refuse(
        destination_problems([output], (), overwrite=run.args.overwrite)
    ):
        return
    with open_session(run) as session:
        fetcher = _FETCHERS[spec.kind]
        result = _cancellable(run, session, lambda: fetcher(session, spec.target))
    if result is None:
        # Only a conditional fetch returns nothing, and the CLI makes none.
        run.fail(None, ReadingListError(f"{spec}: nothing was fetched"))
        return
    print_messages(run.err, result.warnings, f"{spec}: warning")
    run.write(result.reading_list, fmt, output)


def _search(run: _Run) -> None:
    where: str = run.args.where
    query = " ".join(run.args.query)
    with open_session(run) as session:
        if where == _CATALOG_KIND:
            entries = _cancellable(run, session, lambda: session.search_catalog(query))
            if entries:
                print_catalog_entries(run.out, entries)
            found = len(entries)
        else:
            lists = _cancellable(
                run, session, lambda: session.search_metron(name=query)
            )
            if lists:
                print_metron_lists(run.out, lists)
            found = len(lists)
    if not found:
        print_note(run.err, f"No {where} lists match {query!r}.")


_ACTIONS: MappingProxyType[str, Callable[[_Run], None]] = MappingProxyType(
    {
        "print": _print,
        "validate": _validate,
        "convert": _convert,
        "combine": _combine,
        "compare": _compare,
        "from-arcs": _from_arcs,
        "search": _search,
        "fetch": _fetch,
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


def _add_online_options(parser: ArgumentParser) -> None:
    """Add the config file, auth and cache options the main parser has."""
    parser.add_argument(
        "-c",
        "--config",
        metavar="PATH",
        dest="general.config",
        help="A config file to read beside the usual ones.",
    )
    add_online_auth_group(parser)
    add_online_cache_group(parser)


def _add_online_actions(actions: Any) -> None:
    sub = actions.add_parser(
        "search",
        help="Search Metron's reading lists or the DieselTech catalog.",
        description=(
            "Search Metron's reading lists by name (needs a Metron API token),"
            " or the paths of the DieselTech catalog on GitHub."
        ),
        formatter_class=RichHelpFormatter,
    )
    sub.add_argument(
        "where", choices=_SEARCH_WHERE, metavar="metron|catalog", help="Where to look."
    )
    sub.add_argument(
        "query", nargs="+", metavar="QUERY", help="Words the name or path holds."
    )
    _add_online_options(sub)
    sub = actions.add_parser(
        "fetch",
        help="Fetch a list from Metron, the catalog or a URL.",
        description=(
            "Fetch metron:ID (a Metron reading list), metron-arc:ID (a Metron"
            " story arc), catalog:PATH (a DieselTech list) or an http(s) URL,"
            " and write it, to stdout without -o. Metron needs an API token."
        ),
        formatter_class=RichHelpFormatter,
    )
    _add_write_options(sub, "FILE", "Write here, not to stdout.")
    sub.add_argument(
        "spec",
        type=fetch_spec,
        metavar="WHAT",
        help="metron:ID, metron-arc:ID, catalog:PATH or an http(s) URL.",
    )
    _add_online_options(sub)


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
    _add_online_actions(actions)
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
    except (OSError, ReadingListError, ConfigError, ConfigurationError) as exc:
        run.fail(None, exc)
        return 1
    except OnlineLookupAbortedError as exc:
        if not run.cancelled:
            # The gate's own abort, such as a spent daily quota.
            run.fail(None, exc)
            return 1
        print_note(run.err, "Cancelled.")
        return EXIT_CANCELLED
    except KeyboardInterrupt:
        print_note(run.err, "Cancelled.")
        return EXIT_CANCELLED
    return run.exit_code
