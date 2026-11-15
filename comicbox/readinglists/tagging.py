"""
Decide how ``write-arcs`` writes each comic, or why it does not.

A format that cannot hold the arc is refused before anything is read: the
check writes a comic holding only the arc to the format, reads it back and
compares. A comic with a tag file comicbox could not parse is not written,
and a file found under several paths is written once.
"""

from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from comicbox.constants import ROOT_TAG
from comicbox.formats import MetadataFormats
from comicbox.formats.comicbox.schema import ARCS_KEY
from comicbox.readinglists.match import ArcAction, ArcChange
from comicbox.readinglists.schema import ISSUE_KEY, NAME_KEY, NUMBER_KEY, SERIES_KEY

if TYPE_CHECKING:
    from comicbox.config.settings import ComicboxSettings
    from comicbox.readinglists.library import Comic

# What a tag format is called in a message, when not its file's name.
_FORMAT_NAMES = MappingProxyType(
    {
        MetadataFormats.COMIC_BOOK_INFO: "ComicBookInfo comment",
        MetadataFormats.PDF: "PDF metadata",
    }
)


def format_name(fmt: MetadataFormats) -> str:
    """Name a tag format as a comic carries it: its file, or what it is."""
    return _FORMAT_NAMES.get(fmt, fmt.value.filename)


class ArcFit(StrEnum):
    """What a tag format does with an arc written to it."""

    HOLDS = "holds"
    # The format has no arcs: the write leaves the arc out of it.
    NONE = "none"
    # It reads back as something else, such as a ComicInfo arc whose comma
    # splits it in two: the write would put the wrong arcs in it.
    MANGLES = "mangles"


def arc_fit(
    fmt: MetadataFormats,
    name: str,
    number: int | None,
    config: "ComicboxSettings | None" = None,
) -> ArcFit:
    """Write a comic holding only this arc in a format, read it back, compare."""
    from comicbox.box import Comicbox

    arc = {} if number is None else {NUMBER_KEY: number}
    metadata = {
        ROOT_TAG: {
            SERIES_KEY: {NAME_KEY: "Arc check"},
            ISSUE_KEY: {NAME_KEY: "1"},
            ARCS_KEY: {name: arc},
        }
    }
    try:
        text = Comicbox(metadata=metadata, config=config).to_string(fmt)
        read = Comicbox(metadata=text, fmt=fmt, config=config).to_dict()
    except Exception:
        # A format that cannot even write this arc cannot hold it.
        return ArcFit.MANGLES
    arcs = (read.get(ROOT_TAG) or {}).get(ARCS_KEY)
    if not arcs:
        return ArcFit.NONE
    return ArcFit.HOLDS if arcs == {name: arc} else ArcFit.MANGLES


class ArcFits:
    """``arc_fit``, tried once per format and arc name in a run."""

    def __init__(
        self, *, ordered: bool, config: "ComicboxSettings | None" = None
    ) -> None:
        """Check numbered arcs for an ordered list, unnumbered otherwise."""
        self._number = 1 if ordered else None
        self._config = config
        self._fits: dict[tuple[MetadataFormats, str], ArcFit] = {}

    def __call__(self, fmt: MetadataFormats, name: str) -> ArcFit:
        """Say what a format does with this arc."""
        key = (fmt, name)
        if (fit := self._fits.get(key)) is None:
            fit = arc_fit(fmt, name, self._number, self._config)
            self._fits[key] = fit
        return fit


@dataclass(frozen=True, slots=True)
class ArcWrite:
    """
    How one file gets its arc: the formats to write, or why it is not.

    ``formats`` is empty when nothing is written, and ``reason`` then says
    why, unless the comic already has the arc. ``same_file`` lists the
    other paths that are this file.
    """

    change: ArcChange
    formats: frozenset[MetadataFormats] = frozenset()
    reason: str | None = None
    same_file: tuple[Path, ...] = ()

    @property
    def path(self) -> Path:
        """Get the path written."""
        return self.change.path


def plan_write(
    change: ArcChange, comic: "Comic", formats: frozenset[MetadataFormats]
) -> ArcWrite:
    """Decide how to write one comic's arc change in ``formats``."""
    if change.action is ArcAction.TAGGED:
        return ArcWrite(change)
    if comic.unreadable:
        reason = f"its {', '.join(comic.unreadable)} could not be read"
        return ArcWrite(change, reason=reason)
    return ArcWrite(change, formats)


def group_files(
    paths: Collection[Path], key: Callable[[Path], Any]
) -> Mapping[Path, tuple[Path, ...]]:
    """
    Group paths by the file they are; each group's first path names it.

    Returns each first path with the other paths of its file.
    """
    groups: dict[Any, list[Path]] = {}
    for path in sorted(paths):
        groups.setdefault(key(path), []).append(path)
    return {group[0]: tuple(group[1:]) for group in groups.values()}
