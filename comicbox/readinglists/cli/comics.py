"""
The actions on a directory of comics: match a list, and write its arcs.

``write-arcs`` merges the arc into each comic's tags, never writes a comic
with a tag file comicbox could not parse, writes each file once, and checks
each write by reading the comic back. Ctrl-C while comics are read stops at
once; while they are written it only asks, and the writes under way finish.
"""

import threading
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from comicbox.cli.parser import CSVAction
from comicbox.constants import ROOT_TAG
from comicbox.exceptions import ReadingListError
from comicbox.readinglists.arcs import arc_patch
from comicbox.readinglists.cli.run import (
    Run,
    interrupts_ask,
    library_configs,
    read_tagged_comics,
)
from comicbox.readinglists.combine.fields import is_ordered
from comicbox.readinglists.library import TAG_FORMATS, Library
from comicbox.readinglists.match import (
    MatchResult,
    find_arc,
    match_comics,
    plan_arcs,
)
from comicbox.readinglists.render import (
    arc_text,
    print_ambiguous,
    print_arc_write,
    print_matches,
    print_note,
    print_variant_only,
)
from comicbox.readinglists.schema import ENTRIES_KEY, NAME_KEY, NUMBER_KEY
from comicbox.readinglists.tagging import (
    ArcFit,
    ArcFits,
    ArcWrite,
    format_name,
    group_files,
    plan_write,
)

if TYPE_CHECKING:
    from comicbox.config.settings import ComicboxSettings
    from comicbox.formats import MetadataFormats
    from comicbox.write import WriteResult

# -w takes the tag formats comicbox writes into a comic, by config key.
_FORMAT_KEYS = MappingProxyType(
    {key: fmt for fmt in TAG_FORMATS for key in fmt.value.config_keys}
)
_ADDITIVE = "additive"


def _count(number: int, noun: str, plural: str | None = None) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {plural or noun + 's'}"


def _library(run: Run, config: "ComicboxSettings") -> Library | None:
    """Read the comics under the command's directory, or say why not."""
    directory: Path = run.args.directory
    if not directory.is_dir():
        run.fail(directory, ReadingListError("not a directory"))
        return None
    library = read_tagged_comics(run, directory, config)
    if not library.comics and not library.unread_directories:
        print_note(run.err, f"No tagged comics in {directory}.")
    return library


def _tags(library: Library) -> dict[Path, Mapping[str, Any]]:
    return {path: comic.tags for path, comic in library.comics.items()}


def _unreadable(library: Library) -> dict[Path, str]:
    return {
        path: f"unreadable {', '.join(comic.unreadable)}"
        for path, comic in library.comics.items()
        if comic.unreadable
    }


def _match(run: Run) -> None:
    if (loaded := run.load(run.args.file)) is None:
        return
    read_config, _ = library_configs()
    if (library := _library(run, read_config)) is None:
        return
    reading_list = loaded.reading_list
    result = match_comics(reading_list, _tags(library))
    print_matches(
        run.out, reading_list, result, run.args.directory, _unreadable(library)
    )
    total = len(reading_list.get(ENTRIES_KEY) or ())
    print_note(
        run.err,
        f"{len(result.found)} of {total} entries found in"
        f" {_count(len(library.comics), 'comic')}; {len(result.missing)} missing.",
    )
    run.no_keys((run.args.file,), (reading_list,))


# write-arcs


def _requested_formats(run: Run) -> "frozenset[MetadataFormats]":
    """Resolve -w to tag formats; a key that names none is a usage error."""
    formats: set[MetadataFormats] = set()
    for token in run.args.formats:
        if (fmt := _FORMAT_KEYS.get(str(token).strip().lower())) is None:
            run.misuse(
                f"-w {token}: not a tag format comicbox writes into a comic,"
                " such as cix, mi or json"
            )
        else:
            formats.add(fmt)
    if not formats and not run.misused:
        run.misuse("-w names no format")
    return frozenset(formats)


def _refuse_unfit(
    run: Run, formats: "frozenset[MetadataFormats]", name: str, fits: ArcFits
) -> bool:
    """Refuse the run when a -w format cannot hold the arc; say whether."""
    for fmt in sorted(formats, key=lambda fmt: fmt.name):
        if (fit := fits(fmt, name)) is not ArcFit.HOLDS:
            why = (
                "has no story arcs"
                if fit is ArcFit.NONE
                else "reads it back as other arcs"
            )
            run.misuse(f"-w: {format_name(fmt)} cannot hold the arc {name!r}: it {why}")
    return run.misused


@dataclass(frozen=True, slots=True)
class _Plan:
    """What write-arcs will do: one write per file, and what it leaves alone."""

    result: MatchResult
    writes: tuple[ArcWrite, ...]
    variant_only: tuple[Path, ...]
    # Comics not written because their entry fits several volumes: each
    # with the entry's position and the volumes.
    ambiguous: tuple[tuple[Path, int, tuple[int, ...]], ...]

    @property
    def todo(self) -> tuple[ArcWrite, ...]:
        """Get the writes to make."""
        return tuple(write for write in self.writes if write.formats)

    @property
    def refused(self) -> tuple[ArcWrite, ...]:
        """Get the files that are not written, and not for having the arc."""
        return tuple(write for write in self.writes if write.reason is not None)


def _plan(
    run: Run,
    reading_list: Mapping[str, Any],
    library: Library,
    formats: "frozenset[MetadataFormats]",
) -> _Plan:
    from comicbox.box.archive.write import file_key

    tags = _tags(library)
    result = match_comics(reading_list, tags)
    changes = {
        change.path: change
        for change in plan_arcs(
            reading_list,
            tags,
            result,
            reading_list[NAME_KEY],
            variants=run.args.variants,
        )
    }
    writes = tuple(
        replace(
            plan_write(changes[path], library.comics[path], formats),
            same_file=others,
        )
        for path, others in group_files(changes, file_key).items()
    )
    return _Plan(result, writes, *_left_out(result, changes))


def _left_out(
    result: MatchResult, planned: Collection[Path]
) -> tuple[tuple[Path, ...], tuple[tuple[Path, int, tuple[int, ...]], ...]]:
    """List the found comics not planned: by a variant only, and ambiguous."""
    variant_only = sorted(
        {
            comic.path
            for found in result.found
            for comic in found.comics
            if not comic.by.strict and comic.path not in planned
        }
    )
    ambiguous = tuple(
        (comic.path, found.position, found.volumes)
        for found in result.found
        if found.ambiguous
        for comic in found.comics
        if comic.path not in planned
    )
    return tuple(variant_only), ambiguous


def _held(path: Path, write: ArcWrite, config: "ComicboxSettings") -> str | None:
    """Read a written comic back from ``path``; say how it lacks its arc, or None."""
    from comicbox.box import Comicbox

    change = write.change
    try:
        with Comicbox(path, config=config) as box:
            tags = box.to_dict().get(ROOT_TAG) or {}
    except Exception as exc:
        return f"it could not be read back: {exc}"
    if (arc := find_arc(tags, change.arc)) is None:
        return f"it reads back without {change.arc!r}"
    has = arc[1].get(NUMBER_KEY)
    if change.number is not None and has != change.number:
        return f"it reads back with {arc_text(arc[0], has)}"
    return None


def _report(
    run: Run, write: ArcWrite, written: "WriteResult", config: "ComicboxSettings"
) -> bool:
    """Say what one write did; whether the comic now holds its arc."""
    if written.error is not None:
        run.fail(write.path, written.error)
        return False
    if written.cancelled or not written.written:
        why = "cancelled" if written.cancelled else "comicbox wrote nothing"
        print_arc_write(run.out, replace(write, reason=why), done=True)
        # A cancelled run exits 130 whatever else happened.
        run.failed = run.failed or not written.cancelled
        return False
    # A CBR, CBT or CB7 is converted to a CBZ beside it, as any write does.
    final = written.final_path or write.path
    problem = _held(final, write, config)
    moved = final if final != write.path else None
    print_arc_write(run.out, write, done=True, problem=problem, moved=moved)
    if problem is not None:
        run.failed = True
    return problem is None


def _apply(
    run: Run,
    todo: Sequence[ArcWrite],
    write_config: "ComicboxSettings",
    read_config: "ComicboxSettings",
) -> list[ArcWrite]:
    """Make the writes, each additively; return those that hold."""
    from comicbox.write import BulkWriteItem, bulk_write

    by_path = {write.path: write for write in todo}
    items = [
        BulkWriteItem(
            write.path,
            arc_patch(write.change.arc, write.change.number),
            merge_mode=_ADDITIVE,
            formats=frozenset(fmt.name for fmt in write.formats),
        )
        for write in todo
    ]
    held: list[ArcWrite] = []
    cancel = threading.Event()
    with interrupts_ask(run, cancel.set):
        for written in bulk_write(items, cancel=cancel, base_config=write_config):
            write = by_path[written.path]
            if _report(run, write, written, read_config):
                held.append(write)
    return held


def _summary(
    run: Run,
    reading_list: Mapping[str, Any],
    plan: _Plan,
    held: Sequence[ArcWrite] | None,
) -> None:
    """Sum the run up on stderr; ``held`` is None for a dry run."""
    files = _count(len(plan.writes), "matched comic")
    if held is None:
        verdict = f"Dry run: {len(plan.todo)} of {files} would change"
        if run.args.apply:
            verdict += "; general.dry_run is set in the config, so nothing was written."
        else:
            verdict += "; --apply writes them."
    elif not plan.todo:
        verdict = f"Nothing to write among {files}."
    else:
        verdict = f"{len(held)} of {files} written."
    print_note(run.err, verdict)
    counted = (
        (
            len(plan.refused),
            f"{_count(len(plan.refused), 'matched comic')} not written; see above.",
        ),
        (
            len(plan.ambiguous),
            (
                f"{_count(len(plan.ambiguous), 'comic')} not written, for an entry"
                " that fits more than one volume."
            ),
        ),
        (
            len(plan.variant_only),
            (
                f"{_count(len(plan.variant_only), 'comic')} found only by a name"
                " variant; --variants tags them."
            ),
        ),
        (
            len(plan.result.missing),
            f"{_count(len(plan.result.missing), 'entry', 'entries')} matched nothing.",
        ),
    )
    for number, line in counted:
        if number:
            print_note(run.err, line)
    run.no_keys((run.args.file,), (reading_list,))


@dataclass(frozen=True, slots=True)
class _Setup:
    """The list, its arc's name, the configs, and the formats asked for."""

    reading_list: Mapping[str, Any]
    formats: "frozenset[MetadataFormats]"
    read_config: "ComicboxSettings"
    write_config: "ComicboxSettings"


def _setup(run: Run) -> _Setup | None:
    """
    Load the list and check -w, before any comic is read; None to stop.

    A -w format that is not a tag format, or cannot hold the arc, is a
    usage error.
    """
    formats = _requested_formats(run)
    if run.misused or (loaded := run.load(run.args.file)) is None:
        return None
    reading_list = loaded.reading_list
    if not (name := reading_list.get(NAME_KEY)):
        reason = "the list has no name to tag its arc with"
        run.fail(run.args.file, ReadingListError(reason))
        return None
    read_config, write_config = library_configs()
    fits = ArcFits(ordered=is_ordered(reading_list), config=write_config)
    if _refuse_unfit(run, formats, name, fits):
        return None
    return _Setup(reading_list, formats, read_config, write_config)


def _print_plan(run: Run, plan: _Plan, *, applying: bool) -> None:
    """Show each file's change; when applying, only those not to be written."""
    for write in plan.writes:
        if not (applying and write.formats):
            print_arc_write(run.out, write, done=False)
    for path in plan.variant_only:
        print_variant_only(run.out, path)
    for path, position, volumes in plan.ambiguous:
        print_ambiguous(run.out, path, position, volumes)


def _write_arcs(run: Run) -> None:
    if (setup := _setup(run)) is None:
        return
    if (library := _library(run, setup.read_config)) is None:
        return
    plan = _plan(run, setup.reading_list, library, setup.formats)
    if plan.refused or plan.ambiguous:
        run.failed = True
    applying = run.args.apply and not setup.write_config.general.dry_run
    _print_plan(run, plan, applying=applying)
    held = None
    if applying:
        held = _apply(run, plan.todo, setup.write_config, setup.read_config)
    _summary(run, setup.reading_list, plan, held)
    if run.cancelled:
        raise KeyboardInterrupt


def add_comic_actions(actions: Any) -> None:
    """Add the actions on a directory of comics to the parser's subcommands."""
    sub = actions.add_parser(
        "match",
        help="Say which of a list's issues the comics in DIR are, and which are missing.",
        description=(
            "Find each of a list's issues among the comics in DIR: by an issue id,"
            " then by series, year or volume and issue, then by a variant of the"
            " series name. Each comic found is a row, with how it was found."
            " Linked directories are not searched."
        ),
    )
    sub.add_argument("file", type=Path, metavar="FILE", help="The reading list.")
    sub.add_argument(
        "directory", type=Path, metavar="DIR", help="Comics, searched deeply."
    )
    sub = actions.add_parser(
        "write-arcs",
        help="Tag the comics in DIR a list matches with its story arc; a dry run without --apply.",
        description=(
            "Tag each comic in DIR that a list matches with the list's name as a"
            " story arc, numbered by its place in an ordered list. Without --apply"
            " nothing is written: each comic's change is shown. Only comics"
            " matched by id or by series, year or volume and issue are tagged,"
            " unless --variants. A comic that already has the arc with that number"
            " is left alone, as is one with a tag file comicbox cannot read."
        ),
    )
    sub.add_argument(
        "-w",
        "--write",
        action=CSVAction,
        required=True,
        metavar="FORMATS",
        dest="formats",
        help=(
            "The tag formats to write, as comicbox -w takes them: cix, mi,"
            " json... Each must be able to hold the arc."
        ),
    )
    sub.add_argument(
        "--variants",
        action="store_true",
        help="Also tag the comics found only by a variant of the series name.",
    )
    sub.add_argument(
        "--apply",
        action="store_true",
        help="Write the arcs. Without it, only show what would change.",
    )
    sub.add_argument("file", type=Path, metavar="FILE", help="The reading list.")
    sub.add_argument(
        "directory", type=Path, metavar="DIR", help="Comics, searched deeply."
    )


ACTIONS: MappingProxyType[str, Callable[[Run], None]] = MappingProxyType(
    {"match": _match, "write-arcs": _write_arcs}
)
