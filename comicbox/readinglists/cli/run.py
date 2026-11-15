"""
What every ``comicbox readinglist`` action shares.

The run that holds an action's arguments, consoles and failures; the
checks that keep a write off an input or an existing file; and the
worker that makes Ctrl-C a clean cancel.
"""

import os
import signal
import threading
from argparse import ArgumentParser, Namespace
from collections import Counter
from collections.abc import Callable, Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, TypeVar

from comicbox.exceptions import (
    ReadingListError,
)
from comicbox.readinglists.identity import entry_keys
from comicbox.readinglists.library import TAG_FORMATS, Library, read_comics
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

if TYPE_CHECKING:
    from rich.console import Console

    from comicbox.config.settings import ComicboxSettings


_T = TypeVar("_T")

EXIT_USAGE = 2
_QUIET_LOGLEVELS = MappingProxyType({1: "WARNING", 2: "ERROR"})

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
        # A usage error found after parsing, such as a -w format that
        # cannot hold the arc: exit 2, as argparse would.
        self.misused = False
        # Set by the user's Ctrl-C, so a spent quota is not taken for one.
        self.cancelled = False

    @property
    def log_level(self) -> str:
        """Get the logging level -Q asks for."""
        quiet = getattr(self.args, "quiet", 0)
        return _QUIET_LOGLEVELS.get(quiet, "CRITICAL") if quiet else "INFO"

    def fail(self, path: Path | None, error: BaseException) -> None:
        """Report one failure on stderr and carry on."""
        print_error(self.err, path, error)
        self.failed = True

    def misuse(self, message: str) -> None:
        """Report a usage error; the command exits 2."""
        print_error(self.err, None, ReadingListError(message))
        self.misused = True

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
        """2 for a usage error, 1 when any file failed."""
        return EXIT_USAGE if self.misused else int(self.failed)


def _stop_reading(run: Run) -> Callable[[int, object], None]:
    """
    Make the first Ctrl-C stop a read, and the rest do nothing.

    The command exits after it, and a second press, such as the one
    ``uv run`` passes on, interrupted the reader pool's shutdown: the
    process hung with its workers. So the rest are ignored from the first.
    """

    def stop(_signum: int, _frame: object) -> None:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        run.cancelled = True
        raise KeyboardInterrupt

    return stop


def read_tagged_comics(
    run: Run, directory: Path, config: "ComicboxSettings | None" = None
) -> Library:
    """
    Read every comic under a directory, in path order.

    A comic that cannot be read is one error line, and a directory one
    warning line; either way the command exits 1 and the rest are read.
    """
    if config is None:
        from comicbox.config import get_config

        config = get_config(Namespace(comicbox=Namespace()))
    previous = signal.signal(signal.SIGINT, _stop_reading(run))
    try:
        library = read_comics(directory, config, run.fail, log_level=run.log_level)
    finally:
        if not run.cancelled:
            signal.signal(signal.SIGINT, previous)
    for path, error in library.unread_directories.items():
        reason = error.strerror or str(error)
        print_messages(run.err, (f"{path}: {reason}; not searched",), "warning")
        run.failed = True
    return library


def _library_config(
    read_keys: Sequence[str], *, delete_orig: bool = False
) -> "ComicboxSettings":
    from comicbox.config import get_config

    args = {
        "read.formats": list(read_keys),
        "read.except": [],
        "write.delete_all_tags": False,
    }
    settings = get_config(Namespace(comicbox=Namespace(**args)))
    general = replace(
        settings.general,
        metadata=None,
        metadata_cli=None,
        delete_keys=frozenset(),
        delete_orig=settings.general.delete_orig or delete_orig,
    )
    return replace(settings, general=general)


def library_configs(
    *, delete_orig: bool = False
) -> tuple["ComicboxSettings", "ComicboxSettings"]:
    """
    Get the configs to read and to write a directory of comics with.

    Both read every tag format a comic can carry, whatever ``read.formats``
    says, so a tag file comicbox cannot parse is found wherever it is, and
    the formats written are built from all of the comic's tags. The read
    config reads the file name as the user's config says; the write config
    never does, so a write adds only the arc. Neither adds the config's
    ``metadata``, deletes its ``delete_keys`` or deletes all tags.
    ``delete_orig`` sets ``general.delete_orig`` for the writes, as the
    main CLI's ``--delete-orig`` does.
    """
    from comicbox.config import get_config
    from comicbox.formats import MetadataFormats

    tag_keys = sorted(min(fmt.value.config_keys) for fmt in TAG_FORMATS)
    user = get_config(Namespace(comicbox=Namespace()))
    read_keys = list(tag_keys)
    if MetadataFormats.FILENAME in user.read.formats:
        read_keys.append(min(MetadataFormats.FILENAME.value.config_keys))
    return _library_config(read_keys), _library_config(
        tag_keys, delete_orig=delete_orig
    )


_JOIN_POLL_SECONDS = 0.1
EXIT_CANCELLED = 130

FETCH_CANCELLING = "Cancelling before the next request; Ctrl-C again quits now."
WRITE_CANCELLING = "Stopping after the writes under way."
WRITE_STILL_CANCELLING = "Still finishing the writes under way; they are not cut short."


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


@contextmanager
def interrupts_ask(run: Run, cancel: Callable[[], None]) -> Generator[None]:
    """
    Make Ctrl-C only ask the writes to stop, however often it is pressed.

    The first press calls ``cancel``: no new write starts, and the writes
    under way finish. No press raises, so the process never exits with a
    write half done. Must be entered on the main thread.
    """

    def ask(_signum: int, _frame: object) -> None:
        if run.cancelled:
            print_note(run.err, WRITE_STILL_CANCELLING)
            return
        run.cancelled = True
        cancel()
        print_note(run.err, WRITE_CANCELLING)

    previous = signal.signal(signal.SIGINT, ask)
    try:
        yield
    finally:
        # Cancelled, the command now exits: still no press may interrupt it.
        signal.signal(signal.SIGINT, signal.SIG_IGN if run.cancelled else previous)


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
