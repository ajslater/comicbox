"""
Decide how ``write-arcs`` writes each comic, or why it does not.

A format that cannot hold the arc is refused before anything is read: the
check writes a comic holding only the arc to the format, reads it back and
compares. ``-w`` means what it means for comicbox: the formats named are
written and every other tag file is removed, so each write names what it
removes. A CBR, CBT or CB7 is converted to a CBZ, as comicbox converts it.
A comic with a tag file comicbox could not parse is not written, nor one
whose CBZ would land on a file already there, and a file found under
several paths is written once.
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
from comicbox.formats.sources import MetadataSources
from comicbox.readinglists.match import ArcAction, ArcChange
from comicbox.readinglists.schema import ISSUE_KEY, NAME_KEY, NUMBER_KEY, SERIES_KEY

if TYPE_CHECKING:
    from comicbox.config.settings import ComicboxSettings
    from comicbox.predict import WriteDestination
    from comicbox.readinglists.library import Comic

# What a tag format is called in a message, when not its file's name.
_FORMAT_NAMES = MappingProxyType(
    {
        MetadataFormats.COMIC_BOOK_INFO: "ComicBookInfo comment",
        MetadataFormats.PDF: "PDF metadata",
    }
)


# Written in place of the archive's tag files and comment. The PDF metadata
# is kept unless it is one of the formats written.
_KEPT_UNLESS_WRITTEN = frozenset(MetadataSources.ARCHIVE_PDF.value.formats)


def removed_formats(
    carried: Collection[MetadataFormats], written: Collection[MetadataFormats]
) -> frozenset[MetadataFormats]:
    """Get the tag formats a write of ``written`` removes from a comic."""
    return frozenset(carried) - frozenset(written) - _KEPT_UNLESS_WRITTEN


def format_name(fmt: MetadataFormats) -> str:
    """Name a tag format as a comic carries it: its file, or what it is."""
    return _FORMAT_NAMES.get(fmt, fmt.value.filename)


def format_names(formats: Collection[MetadataFormats]) -> str:
    """Name some tag formats, in a stable order."""
    return ", ".join(sorted(format_name(fmt) for fmt in formats))


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
    why, unless the comic already has the arc. ``removes`` names the tag
    files the write takes out of the comic, and ``clears_comment`` whether it
    clears a free-text archive comment. ``converts_to`` is the CBZ a CBR,
    CBT or CB7 is converted to, and ``deletes_original`` whether the
    original then goes. ``same_file`` lists the other paths of this file:
    when the original goes, so do they.
    """

    change: ArcChange
    formats: frozenset[MetadataFormats] = frozenset()
    reason: str | None = None
    same_file: tuple[Path, ...] = ()
    removes: tuple[str, ...] = ()
    converts_to: Path | None = None
    deletes_original: bool = False
    clears_comment: bool = False

    @property
    def loses(self) -> bool:
        """Whether the write takes a tag file or the archive comment away."""
        return bool(self.removes) or self.clears_comment

    @property
    def path(self) -> Path:
        """Get the path written."""
        return self.change.path


def _unwritable(comic: "Comic", destination: "WriteDestination | None") -> str | None:
    """Say why a comic is not written whatever the formats, or None."""
    if comic.unreadable:
        return f"its {', '.join(comic.unreadable)} could not be read"
    if destination is not None and destination.converts and destination.occupied:
        return f"{destination.destination.name} already exists"
    return None


def _formats_written(
    comic: "Comic", formats: frozenset[MetadataFormats], *, keep: bool
) -> tuple[frozenset[MetadataFormats], frozenset[MetadataFormats]]:
    """Get the formats a write writes, and those it removes from the comic."""
    if keep:
        return formats | comic.formats, frozenset()
    return formats, removed_formats(comic.formats, formats)


def _converts_to(destination: "WriteDestination | None") -> Path | None:
    """Get the CBZ a write converts the comic to, or None for one in place."""
    if destination is None or not destination.converts:
        return None
    return destination.destination


def _kept_unfit(
    comic: "Comic",
    named: frozenset[MetadataFormats],
    fits: Callable[[MetadataFormats], ArcFit] | None,
) -> str | None:
    """
    Say why a keep write would put the wrong arcs in a comic, or None.

    A format it keeps that has no arcs is harmless; one that reads the arc
    back as other arcs is not. The formats named were checked for the run.
    """
    if fits is None:
        return None
    for fmt in sorted(comic.formats - named, key=format_name):
        if fits(fmt) is ArcFit.MANGLES:
            return f"its {format_name(fmt)} would read the arc back as other arcs"
    return None


def _none_holds(
    comic: "Comic",
    written: Collection[MetadataFormats],
    fits: Callable[[MetadataFormats], ArcFit] | None,
) -> str | None:
    """Say why a keep write could not hold the arc in any format, or None."""
    if fits is None or any(fits(fmt) is ArcFit.HOLDS for fmt in written):
        return None
    have = format_names(comic.formats) or "no tag file"
    return f"it has {have}, none of which can hold the arc"


def _keep_refusal(
    comic: "Comic",
    formats: frozenset[MetadataFormats],
    written: Collection[MetadataFormats],
    fits: Callable[[MetadataFormats], ArcFit] | None,
) -> str | None:
    """Say why a keep write is not made, or None."""
    return _kept_unfit(comic, formats, fits) or _none_holds(comic, written, fits)


def plan_write(
    change: ArcChange,
    comic: "Comic",
    formats: frozenset[MetadataFormats],
    destination: "WriteDestination | None",
    *,
    delete_orig: bool = False,
    keep: bool = False,
    fits: Callable[[MetadataFormats], ArcFit] | None = None,
) -> ArcWrite:
    """
    Decide how to write one comic's arc change in ``formats``.

    ``destination`` is where comicbox would write it, as
    ``predict_write_destination`` says; None for a comic already tagged.
    With ``keep`` the comic is written in ``formats`` and every format it
    carries, and removes none; ``fits`` says what a kept one does with the
    arc. At least one written must hold it, and none kept may read it back
    as other arcs.
    """
    if change.action is ArcAction.TAGGED:
        return ArcWrite(change)
    if reason := _unwritable(comic, destination):
        return ArcWrite(change, reason=reason)
    written, removed = _formats_written(comic, formats, keep=keep)
    if keep and (reason := _keep_refusal(comic, formats, written, fits)):
        return ArcWrite(change, reason=reason)
    converts_to = _converts_to(destination)
    return ArcWrite(
        change,
        written,
        removes=tuple(sorted(format_name(fmt) for fmt in removed)),
        converts_to=converts_to,
        deletes_original=converts_to is not None and delete_orig,
        # comicbox writes no comment but ComicBookInfo, which holds no arc.
        clears_comment=comic.free_comment and not keep,
    )


def group_files(
    paths: Collection[Path], key: Callable[[Path], Any]
) -> Mapping[Path, tuple[Path, ...]]:
    """
    Group paths by the file they are; each group's first path names it.

    The first is the first in path order that is not a symbolic link, or
    the first link when all are. Returns each first path with the other
    paths of its file.
    """
    groups: dict[Any, list[Path]] = {}
    for path in sorted(paths):
        groups.setdefault(key(path), []).append(path)
    named = {}
    for group in groups.values():
        first = min(group, key=lambda path: (path.is_symlink(), path))
        named[first] = tuple(path for path in group if path != first)
    return named
