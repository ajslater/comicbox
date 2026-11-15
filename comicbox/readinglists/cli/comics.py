"""The actions on a directory of comics: match a list, and write its arcs."""

import sys
import threading
from argparse import Namespace
from collections.abc import Callable, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from comicbox.cli.parser import (
    CSVAction,
)
from comicbox.exceptions import (
    ReadingListError,
)
from comicbox.readinglists.arcs import arc_patch
from comicbox.readinglists.match import (
    ArcAction,
    ArcChange,
    match_comics,
    plan_arcs,
)
from comicbox.readinglists.render import (
    print_arc_change,
    print_matches,
    print_note,
    print_status,
)
from comicbox.readinglists.schema import ENTRIES_KEY, NAME_KEY

if sys.version_info >= (3, 12):
    pass  # pyright: ignore[reportUnreachable]
else:
    pass

if TYPE_CHECKING:
    from comicbox.config.settings import ComicboxSettings
from comicbox.readinglists.cli.run import (
    WRITE_CANCELLING,
    Run,
    cancellable,
    read_tagged_comics,
)


def _comics(run: Run) -> dict[Path, dict[str, Any]] | None:
    """Read the comics under the command's directory, or say why not."""
    directory: Path = run.args.directory
    if not directory.is_dir():
        run.fail(directory, ReadingListError("not a directory"))
        return None
    comics = read_tagged_comics(run, directory)
    if not comics:
        print_note(run.err, f"No tagged comics in {directory}.")
    return comics


def _match(run: Run) -> None:
    if (loaded := run.load(run.args.file)) is None:
        return
    if (comics := _comics(run)) is None:
        return
    reading_list = loaded.reading_list
    result = match_comics(reading_list, comics)
    print_matches(run.out, reading_list, result, run.args.directory)
    total = len(reading_list.get(ENTRIES_KEY) or ())
    print_note(
        run.err,
        f"{len(result.found)} of {total} entries found in {len(comics)} comics;"
        f" {len(result.missing)} missing.",
    )
    run.no_keys((run.args.file,), (reading_list,))


def _write_formats(run: Run) -> "tuple[frozenset[str], ComicboxSettings] | None":
    """Resolve ``-w`` as the main CLI does; refuse it when none is known."""
    from comicbox.config import get_config

    dests = {"write.formats": run.args.formats}
    settings = get_config(Namespace(comicbox=Namespace(**dests)))
    if not (formats := frozenset(fmt.name for fmt in settings.write.formats)):
        reason = "-w names no format comicbox writes, such as cix, mi or json"
        run.fail(None, ReadingListError(reason))
        return None
    return formats, settings


def _report_write(run: Run, change: ArcChange, written: Any) -> None:
    """Say what one write did, or why it did not."""
    if written.error is not None:
        run.fail(change.path, written.error)
    elif written.cancelled:
        print_status(run.out, change.path, ok=False, detail="not written: cancelled")
    elif written.written:
        final = written.final_path
        moved = f" as {final.name}" if final and final != change.path else ""
        print_arc_change(run.out, change, done=True, suffix=moved)
    else:
        print_status(run.out, change.path, ok=False, detail="not written")
        run.failed = True


def _apply_arcs(
    run: Run,
    changes: Sequence[ArcChange],
    formats: frozenset[str],
    settings: "ComicboxSettings",
) -> None:
    """Write the changes; one comic that fails does not stop the rest."""
    from comicbox.write import BulkWriteItem, bulk_write

    cancel = threading.Event()
    by_path = {change.path: change for change in changes}
    items = [
        BulkWriteItem(
            change.path, arc_patch(change.arc, change.number), formats=formats
        )
        for change in changes
    ]

    def write_all() -> None:
        for written in bulk_write(items, cancel=cancel, base_config=settings):
            _report_write(run, by_path[written.path], written)

    cancellable(run, cancel.set, write_all, WRITE_CANCELLING)
    if run.cancelled:
        raise KeyboardInterrupt


def _plan_arcs(run: Run) -> tuple[ArcChange, ...] | None:
    """Plan each matched comic's arc, or say why there is no plan."""
    if (loaded := run.load(run.args.file)) is None:
        return None
    reading_list = loaded.reading_list
    if not (name := reading_list.get(NAME_KEY)):
        reason = "the list has no name to tag its arc with"
        run.fail(run.args.file, ReadingListError(reason))
        return None
    if (comics := _comics(run)) is None:
        return None
    result = match_comics(reading_list, comics)
    return plan_arcs(reading_list, comics, result, name)


def _write_arcs(run: Run) -> None:
    if (resolved := _write_formats(run)) is None:
        return
    if (changes := _plan_arcs(run)) is None:
        return
    todo = [change for change in changes if change.action is not ArcAction.TAGGED]
    for change in changes:
        if change.action is ArcAction.TAGGED or not run.args.apply:
            print_arc_change(run.out, change, done=False)
    if not run.args.apply:
        print_note(
            run.err,
            f"Dry run: {len(todo)} of {len(changes)} matched comics would change;"
            " --apply writes them.",
        )
        return
    _apply_arcs(run, todo, *resolved)


def add_comic_actions(actions: Any) -> None:
    """Add the actions on a directory of comics to the parser's subcommands."""
    sub = actions.add_parser(
        "match",
        help="Say which of a list's issues the comics in DIR are, and which are missing.",
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
            " nothing is written: each comic's change is shown. A comic that already"
            " has the arc with that number is left alone."
        ),
    )
    sub.add_argument(
        "-w",
        "--write",
        action=CSVAction,
        required=True,
        metavar="FORMATS",
        dest="formats",
        help="The tag formats to write, as comicbox -w takes them: cix, mi, json...",
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
