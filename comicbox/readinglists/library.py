"""
Read a directory of comics, to match a list against them and tag them.

Each comic is read in a pool of worker processes. Besides its tags, a read
records the tag formats the comic carries, so a write can name the ones it
removes, and the tag files comicbox could not parse: a write would replace
them with what was read from the rest, so such a comic is never written.

The workers never take Ctrl-C: it goes to this process alone, which stops
the read. Before, every worker printed its own traceback.
"""

import os
import signal
from collections import Counter
from collections.abc import Callable, Generator, Iterator, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from loguru import logger

from comicbox.box import Comicbox
from comicbox.constants import ROOT_TAG
from comicbox.enums.comicbox import FileTypeEnum
from comicbox.formats import MetadataFormats
from comicbox.formats.sources import MetadataSources

if TYPE_CHECKING:
    from comicbox.box.init import SourceData
    from comicbox.config.settings import ComicboxSettings

OnError = Callable[[Path, BaseException], None]

# The sources that are files in, or metadata of, the archive itself.
_TAG_SOURCES = (
    MetadataSources.ARCHIVE_FILE,
    MetadataSources.ARCHIVE_COMMENT,
    MetadataSources.ARCHIVE_PDF,
)
TAG_FORMATS = frozenset(
    fmt for source in _TAG_SOURCES for fmt in source.value.formats if fmt.value.enabled
)
_COMIC_SUFFIXES = frozenset(f".{file_type.value.lower()}" for file_type in FileTypeEnum)
_SOURCE_NAMES = MappingProxyType(
    {
        MetadataSources.ARCHIVE_COMMENT: "archive comment",
        MetadataSources.ARCHIVE_PDF: "PDF metadata",
    }
)


@dataclass(frozen=True, slots=True)
class Comic:
    """
    One comic's tags, and its tag files.

    ``formats`` are the tag formats it carries that comicbox read, and
    ``unreadable`` names the tag files it carries that comicbox could not
    parse.
    """

    tags: dict[str, Any]
    formats: frozenset[MetadataFormats] = frozenset()
    unreadable: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Library:
    """The comics under a directory, by path, and why any directory went unread."""

    comics: dict[Path, Comic] = field(default_factory=dict)
    unread_directories: dict[Path, OSError] = field(default_factory=dict)


def _source_name(source: MetadataSources, data: "SourceData") -> str:
    if source is MetadataSources.ARCHIVE_FILE and data.path:
        return Path(data.path).name
    return _SOURCE_NAMES.get(source, source.value.label)


def _is_json(text: Any) -> bool:
    """Tell an archive comment that tries to be JSON from free text."""
    if isinstance(text, bytes):
        text = text.decode(errors="replace")
    return isinstance(text, str) and text.lstrip().startswith("{")


def _tag_files(box: Comicbox) -> tuple[frozenset[MetadataFormats], tuple[str, ...]]:
    """
    Get the tag formats a comic carries, and name the files that did not parse.

    An archive comment of free text is not a tag file, so it is neither.
    """
    formats: set[MetadataFormats] = set()
    unreadable: list[str] = []
    for source in _TAG_SOURCES:
        loaded = Counter(
            (str(metadata.path), metadata.fmt)
            for metadata in box.get_loaded_metadata(source) or ()
        )
        for data in box.get_source_metadata(source) or ():
            key = (str(data.path), data.fmt)
            if loaded[key]:
                loaded[key] -= 1
                if data.fmt is not None:
                    formats.add(data.fmt)
            elif source is not MetadataSources.ARCHIVE_COMMENT or _is_json(data.data):
                unreadable.append(_source_name(source, data))
    return frozenset(formats), tuple(unreadable)


def _read_comic(path: Path, config: "ComicboxSettings | None") -> Comic:
    """Read one comic's tags and tag files (runs in a worker process)."""
    with Comicbox(path, config=config) as box:
        tags = box.to_dict().get(ROOT_TAG) or {}
        # A tag file that failed to load is loaded again when asked for, and
        # warned of again: the read above has warned of it once.
        logger.disable("comicbox")
        try:
            formats, unreadable = _tag_files(box)
        finally:
            logger.enable("comicbox")
        return Comic(dict(tags), formats, unreadable)


def _init_worker(log_level: str) -> None:
    """Leave Ctrl-C to the parent, and log at its level (in a worker)."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    from comicbox.logger import init_logging

    init_logging(log_level, sink="stderr")


@contextmanager
def _interrupts_blocked() -> Generator[None]:
    """
    Start workers with Ctrl-C blocked, so none takes it while it starts up.

    A worker started meanwhile keeps the block, and its initializer then
    ignores the signal too. Here a press is only held back, not lost: it
    arrives when the block is lifted.
    """
    if not hasattr(signal, "pthread_sigmask"):
        yield
        return
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT})
    try:
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)


def comic_paths(
    directory: Path, on_error: Callable[[Path, OSError], None]
) -> list[Path]:
    """
    List the comic archives under a directory, in path order.

    A linked file is listed; a linked directory is not searched, as with
    comicbox's ``--recurse``. A directory that cannot be read goes to
    ``on_error``.
    """

    def report(error: OSError) -> None:
        on_error(Path(error.filename) if error.filename else directory, error)

    paths = [
        Path(root) / name
        for root, _directories, names in os.walk(directory, onerror=report)
        for name in names
        if Path(name).suffix.lower() in _COMIC_SUFFIXES
    ]
    return sorted(path for path in paths if path.is_file())


def _read_all(
    paths: Sequence[Path], config: "ComicboxSettings | None", log_level: str
) -> Iterator[tuple[Path, Comic | BaseException]]:
    pool = ProcessPoolExecutor(initializer=_init_worker, initargs=(log_level,))
    try:
        with _interrupts_blocked():
            futures = {pool.submit(_read_comic, path, config): path for path in paths}
        for future in as_completed(futures):
            try:
                yield futures[future], future.result()
            except Exception as exc:
                # Whatever stopped one comic's read is that comic's error.
                yield futures[future], exc
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def read_comics(
    directory: Path,
    config: "ComicboxSettings | None" = None,
    on_error: OnError | None = None,
    *,
    log_level: str = "INFO",
) -> Library:
    """
    Read every comic under a directory, in path order.

    A comic that cannot be read goes to ``on_error`` and the rest are read;
    a directory that cannot be read is in ``unread_directories``. A comic
    with no tags is left out: there is nothing to match it by.
    ``log_level`` is the workers' logging level.
    """
    unread: dict[Path, OSError] = {}
    comics: dict[Path, Comic] = {}
    if paths := comic_paths(directory, unread.__setitem__):
        for path, read in _read_all(paths, config, log_level):
            if isinstance(read, BaseException):
                if on_error is not None:
                    on_error(path, read)
            elif read.tags:
                comics[path] = read
    return Library(
        {path: comics[path] for path in sorted(comics)},
        {path: unread[path] for path in sorted(unread)},
    )
