"""
What every ``comicbox readinglist`` action shares.

The run that holds an action's arguments, consoles and failures; the
checks that keep a write off an input or an existing file; and the
worker that makes Ctrl-C a clean cancel.
"""

import os
import sys
import threading
from argparse import ArgumentParser, Namespace
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

from comicbox.exceptions import (
    ReadingListError,
)
from comicbox.readinglists.identity import entry_keys
from comicbox.readinglists.match import (
    read_comics,
)
from comicbox.readinglists.registry import (
    ReadingListFormats,
)
from comicbox.readinglists.render import (
    console,
    print_error,
    print_messages,
    print_note,
    print_status,
)
from comicbox.readinglists.schema import ENTRIES_KEY
from comicbox.readinglists.serialize import (
    ReadingListResult,
    dumps,
    load,
    lost_fields,
)

if sys.version_info >= (3, 12):
    pass  # pyright: ignore[reportUnreachable]
else:
    pass

if TYPE_CHECKING:
    from rich.console import Console


_T = TypeVar("_T")

DEFAULT_FORMAT = ReadingListFormats.YAML
FORMAT_TOKENS = tuple(
    sorted(token for fmt in ReadingListFormats for token in fmt.value.tokens)
)


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


class Run:
    """One command: its arguments, its consoles and whether anything failed."""

    def __init__(self, args: Namespace) -> None:
        """Hold the parsed arguments; open the consoles."""
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


def read_tagged_comics(run: Run, directory: Path) -> dict[Path, dict[str, Any]]:
    """Read every comic's tags under a directory, in path order."""
    from comicbox.config import get_config

    config = get_config(Namespace(comicbox=Namespace()))
    return read_comics(directory, config, run.fail)


_JOIN_POLL_SECONDS = 0.1
EXIT_CANCELLED = 130

FETCH_CANCELLING = "Cancelling before the next request; Ctrl-C again quits now."
WRITE_CANCELLING = "Stopping after the writes under way; Ctrl-C again quits now."


def cancellable(
    run: Run,
    cancel: Callable[[], None],
    call: Callable[[], _T],
    cancelling: str = FETCH_CANCELLING,
) -> _T:
    """
    Run ``call`` on a worker so the first Ctrl-C cancels it cleanly.

    The first Ctrl-C calls ``cancel`` and says ``cancelling``; the work
    stops at its next safe point, which for a fetch can wait out one
    rate-limit window. A second Ctrl-C quits at once.
    """
    outcome: list[Any] = []

    def work() -> None:
        try:
            outcome.append((True, call()))
        except BaseException as exc:
            outcome.append((False, exc))

    worker = threading.Thread(target=work, name="readinglist-work", daemon=True)
    try:
        # Started inside the try: a Ctrl-C the moment the work begins must
        # still cancel it, not leave it running.
        worker.start()
        while worker.is_alive():
            worker.join(_JOIN_POLL_SECONDS)
    except KeyboardInterrupt:
        run.cancelled = True
        cancel()
        print_note(run.err, cancelling)
        while worker.is_alive():
            worker.join(_JOIN_POLL_SECONDS)
    if not outcome:
        # Interrupted before the work could start: nothing was done.
        raise KeyboardInterrupt
    ok, value = outcome[0]
    if not ok:
        raise value
    return value


def add_write_options(parser: ArgumentParser, output: str, help_text: str) -> None:
    """Add ``--to``, ``-o`` and ``--overwrite`` to an action."""
    parser.add_argument(
        "--to",
        choices=FORMAT_TOKENS,
        default=DEFAULT_FORMAT.name.lower(),
        metavar="FMT",
        help=f"The format to write, yaml by default. One of: {', '.join(FORMAT_TOKENS)}.",
    )
    parser.add_argument("-o", "--output", type=Path, metavar=output, help=help_text)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace files that exist. An input is never written over.",
    )
