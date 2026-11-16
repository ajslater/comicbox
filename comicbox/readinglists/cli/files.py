"""The actions on list files: print, validate, convert, combine, compare, from-arcs."""

import re
from collections.abc import Callable
from pathlib import Path
from types import MappingProxyType
from typing import Any

from comicbox.exceptions import (
    ReadingListError,
)
from comicbox.readinglists.arcs import reading_lists_from_comics
from comicbox.readinglists.cli.run import (
    Run,
    add_write_options,
    destination_problems,
    read_tagged_comics,
)
from comicbox.readinglists.combine import combine
from comicbox.readinglists.compare import compare
from comicbox.readinglists.registry import (
    ReadingListFormats,
    as_text,
    get_format,
)
from comicbox.readinglists.render import (
    print_combine_report,
    print_comparison,
    print_messages,
    print_reading_list,
    print_status,
)
from comicbox.readinglists.schema import ENTRIES_KEY, NAME_KEY
from comicbox.readinglists.serialize import (
    loads,
    readable_depth,
    resolve_format,
)

_UNSAFE_FILENAME_RE = re.compile(r'[\x00-\x1f/\\:*?"<>|]+')
_LIST_FILES = "Reading list files: .cbl, json-cbl, or comicbox YAML or JSON."


def _print(run: Run) -> None:
    for path in run.args.files:
        if result := run.load(path):
            print_reading_list(run.out, path, result)


def _validate_one(run: Run, path: Path) -> None:
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


def _validate(run: Run) -> None:
    for path in run.args.files:
        try:
            _validate_one(run, path)
        except (OSError, ReadingListError) as exc:
            print_status(run.out, path, ok=False, detail=str(exc))
            run.failed = True


def _output_path(source: Path, fmt: ReadingListFormats, directory: Path | None) -> Path:
    return (directory or source.parent) / (source.stem + fmt.value.suffix)


def _convert(run: Run) -> None:
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


def _combine(run: Run) -> None:
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


def _compare(run: Run) -> None:
    if (a := run.load(run.args.a)) and (b := run.load(run.args.b)):
        print_comparison(run.out, compare(a.reading_list, b.reading_list))
        run.no_keys((run.args.a, run.args.b), (a.reading_list, b.reading_list))


def _list_filename(name: str, taken: set[str]) -> str:
    """Name a list's file after it, never twice in one directory."""
    stem = _UNSAFE_FILENAME_RE.sub("_", name).strip(" .") or "reading-list"
    candidate, number = stem, 1
    while candidate.casefold() in taken:
        number += 1
        candidate = f"{stem} {number}"
    taken.add(candidate.casefold())
    return candidate


def _from_arcs(run: Run) -> None:
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
        for reading_list in reading_lists_from_comics(
            comic.tags for comic in read_tagged_comics(run, directory).comics.values()
        )
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


def add_file_actions(actions: Any) -> None:
    """Add the actions on list files to the parser's subcommands."""
    sub = actions.add_parser("print", help="Print each list as a table.")
    sub.add_argument("files", nargs="+", type=Path, metavar="FILE", help=_LIST_FILES)
    sub = actions.add_parser("validate", help="Check each file against its format.")
    sub.add_argument("files", nargs="+", type=Path, metavar="FILE", help=_LIST_FILES)
    sub = actions.add_parser("convert", help="Write each list in another format.")
    add_write_options(sub, "DIR", "Write here, not beside each input.")
    sub.add_argument("files", nargs="+", type=Path, metavar="FILE", help=_LIST_FILES)
    sub = actions.add_parser(
        "combine", help="Combine lists of one reading order, primary first."
    )
    add_write_options(sub, "FILE", "Write here, not to stdout.")
    sub.add_argument(
        "primary", type=Path, metavar="PRIMARY", help="The list whose order is kept."
    )
    sub.add_argument(
        "others",
        nargs="+",
        type=Path,
        metavar="OTHER",
        help="Lists of the same reading order, in rank order.",
    )
    sub = actions.add_parser("compare", help="Say whether two lists are the same list.")
    sub.add_argument("a", type=Path, metavar="A", help="A reading list file.")
    sub.add_argument("b", type=Path, metavar="B", help="Another reading list file.")
    sub = actions.add_parser(
        "from-arcs",
        help="Write one list per story arc the comics in DIR are tagged with.",
    )
    add_write_options(sub, "DIR", "Write here, not the current directory.")
    sub.add_argument(
        "directory", type=Path, metavar="DIR", help="Comics, searched deeply."
    )


ACTIONS: MappingProxyType[str, Callable[[Run], None]] = MappingProxyType(
    {
        "print": _print,
        "validate": _validate,
        "convert": _convert,
        "combine": _combine,
        "compare": _compare,
        "from-arcs": _from_arcs,
    }
)
