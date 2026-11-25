"""
Print reading lists, comparisons and combine reports for the CLI.

Every cell is a `Text` with a `Style`, never markup, and the consoles do
not highlight: series names and paths carry brackets (``[Marvel] Civil
War``) that markup would swallow or misread.
"""

import os
import sys
from collections.abc import Mapping, Sequence
from contextlib import suppress
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.style import Style
from rich.table import Table
from rich.text import Text

from comicbox.formats.comicbox.schema import (
    COVER_DATE_KEY,
    SERIES_START_YEAR_KEY,
    YEAR_KEY,
)
from comicbox.readinglists.combine import CombineResult
from comicbox.readinglists.compare import Comparison
from comicbox.readinglists.identity import YEAR_LIKE_VOLUME
from comicbox.readinglists.schema import (
    DATE_KEY,
    DESCRIPTION_KEY,
    END_YEAR_KEY,
    ENTRIES_KEY,
    ENTRY_TYPE_KEY,
    IDENTIFIERS_KEY,
    ISSUE_KEY,
    LIST_TYPE_KEY,
    NAME_KEY,
    NEXT_KEY,
    NOTES_KEY,
    NUMBER_KEY,
    ORDERED_KEY,
    PREVIOUS_KEY,
    PRIVATE_KEY,
    SERIES_KEY,
    SOURCE_CURATOR_KEY,
    SOURCE_KEY_KEY,
    SOURCE_KIND_KEY,
    SOURCES_KEY,
    START_YEAR_KEY,
    TAGS_KEY,
    VOLUME_KEY,
)
from comicbox.readinglists.serialize import ReadingListResult
from comicbox.readinglists.text import printable
from comicbox.readinglists.transform import entry_issue_name

if sys.version_info >= (3, 12):
    from typing import override  # pyright: ignore[reportUnreachable]
else:
    from typing_extensions import override

if TYPE_CHECKING:
    from comicbox.readinglists.formats.metron_api import MetronListSummary
    from comicbox.readinglists.match import Found, FoundComic, MatchResult, Refused
    from comicbox.readinglists.sources.catalog import CatalogEntry
    from comicbox.readinglists.tagging import ArcWrite

_PLAIN = Style()
_TITLE = Style(bold=True)
_LABEL = Style(color="cyan")
_DIM = Style(dim=True)
_OK = Style(color="green")
_WARN = Style(color="yellow")
_ERROR = Style(color="red", bold=True)


# Wide enough that a table written to a file or a pipe is never wrapped.
_UNWRAPPED_WIDTH = 10_000


class _Console(Console):
    """A console whose reader going away is not an error."""

    @override
    def on_broken_pipe(self) -> None:
        """
        Print nothing more, and let the command finish.

        Rich exits 1 here, so ``rl print FILE | head -1`` failed, and a
        ``write-arcs --apply`` piped into ``head`` stopped tagging part way.
        What was closed now reads nothing: the rest of the output, and
        Python's flush of it at exit, go nowhere.
        """
        self.quiet = True
        with suppress(OSError, ValueError):
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, self.file.fileno())


def console(*, stderr: bool = False) -> Console:
    """
    Get a console that prints text as given.

    Text is not wrapped: a long path stays on its line, and a terminal
    wraps it. A table fits a terminal's width; written anywhere else, it is
    not wrapped at all, so each row stays one line for a script to read.
    """
    out = _Console(highlight=False, soft_wrap=True, stderr=stderr)
    if out.is_terminal:
        return out
    return _Console(
        highlight=False, soft_wrap=True, stderr=stderr, width=_UNWRAPPED_WIDTH
    )


def _text(value: Any, style: Style = _PLAIN) -> Text:
    # printable: names, paths and errors come from outside, and an escape
    # sequence in one would reach the terminal.
    return Text("" if value is None else printable(str(value)), style=style)


def _ids(identifiers: Mapping[str, Any] | None) -> str:
    return ", ".join(
        f"{source}:{identifier.get('key', '')}"
        for source, identifier in (identifiers or {}).items()
    )


def _entry_cells(position: int, entry: Mapping[str, Any]) -> list[Text]:
    series = entry.get(SERIES_KEY) or {}
    volume = series.get(SERIES_START_YEAR_KEY) or (entry.get(VOLUME_KEY) or {}).get(
        NUMBER_KEY
    )
    entry_date = entry.get(DATE_KEY) or {}
    when = entry_date.get(COVER_DATE_KEY) or entry_date.get(YEAR_KEY)
    return [
        _text(position, _DIM),
        _text(series.get(NAME_KEY)),
        _text(volume),
        _text(entry_issue_name(entry) if entry.get(ISSUE_KEY) else ""),
        _text(when),
        _text(entry.get(ENTRY_TYPE_KEY)),
        _text(_ids(entry.get(IDENTIFIERS_KEY)), _DIM),
    ]


def entries_table(reading_list: Mapping[str, Any]) -> Table:
    """Tabulate a list's entries in reading order."""
    table = Table(box=None, pad_edge=False)
    for column in ("#", "Series", "Year/Vol", "Issue", "Date", "Type", "Ids"):
        table.add_column(Text(column, style=_LABEL))
    for position, entry in enumerate(reading_list.get(ENTRIES_KEY) or (), start=1):
        table.add_row(*_entry_cells(position, entry))
    return table


def _source_text(source: Mapping[str, Any]) -> str:
    parts = [source.get(SOURCE_KIND_KEY) or "?"]
    if key := source.get(SOURCE_KEY_KEY):
        parts.append(f"#{key}")
    if curator := source.get(SOURCE_CURATOR_KEY):
        parts.append(f"by {curator}")
    return " ".join(parts)


def _years(reading_list: Mapping[str, Any]) -> str:
    return "-".join(
        str(year)
        for key in (START_YEAR_KEY, END_YEAR_KEY)
        if (year := reading_list.get(key)) is not None
    )


def _ref_name(reading_list: Mapping[str, Any], key: str) -> str | None:
    return (reading_list.get(key) or {}).get(NAME_KEY)


def _header_rows(reading_list: Mapping[str, Any]) -> list[tuple[str, Any]]:
    sources = reading_list.get(SOURCES_KEY) or ()
    rows: list[tuple[str, Any]] = [
        ("Description", reading_list.get(DESCRIPTION_KEY)),
        ("Type", reading_list.get(LIST_TYPE_KEY)),
        ("Ordered", reading_list.get(ORDERED_KEY)),
        ("Private", reading_list.get(PRIVATE_KEY)),
        ("Years", _years(reading_list)),
        ("Previous", _ref_name(reading_list, PREVIOUS_KEY)),
        ("Next", _ref_name(reading_list, NEXT_KEY)),
        ("Tags", ", ".join(sorted(reading_list.get(TAGS_KEY) or ()))),
        ("Notes", reading_list.get(NOTES_KEY)),
        *(("Source", _source_text(source)) for source in sources),
        ("Entries", len(reading_list.get(ENTRIES_KEY) or ())),
    ]
    return [row for row in rows if row[1] not in (None, "")]


def header_table(reading_list: Mapping[str, Any]) -> Table:
    """Tabulate a list's header."""
    table = Table(box=None, show_header=False, pad_edge=False)
    table.add_column(style=_LABEL)
    table.add_column()
    for label, value in _header_rows(reading_list):
        table.add_row(_text(label, _LABEL), _text(value))
    return table


def print_messages(out: Console, messages: Sequence[str], label: str) -> None:
    """Print warnings or losses, one per line."""
    for message in messages:
        out.print(Text.assemble((f"{label}: ", _WARN), (printable(message), _PLAIN)))


def print_note(out: Console, message: str) -> None:
    """Print a line about what is going on, dimmed."""
    out.print(_text(message, _DIM))


def print_error(out: Console, path: Path | str | None, error: BaseException) -> None:
    """Print a failure in one line, naming its file once."""
    message = str(error)
    if isinstance(error, OSError) and error.strerror:
        path = error.filename if error.filename is not None else path
        message = error.strerror
    prefix = f"{path}: " if path else ""
    out.print(Text.assemble((printable(prefix), _PLAIN), (printable(message), _ERROR)))


def print_reading_list(out: Console, path: Path, result: ReadingListResult) -> None:
    """Print a list's name, header and entries."""
    label = f" ({result.fmt.value.label})" if result.fmt else ""
    out.print(_text(f"{path}{label}", _DIM))
    # The name on a line of its own: as a table title it wraps to the table.
    out.print(_text(result.reading_list.get(NAME_KEY) or "(unnamed)", _TITLE))
    out.print(header_table(result.reading_list))
    out.print(entries_table(result.reading_list))


def print_status(out: Console, path: Path | str, ok: bool, detail: str) -> None:  # noqa: FBT001
    """Print one line: a mark, the path and what was found."""
    mark = Text("✓ ", style=_OK) if ok else Text("✗ ", style=_ERROR)
    out.print(
        Text.assemble(
            mark, (printable(str(path)), _PLAIN), (printable(f" {detail}"), _DIM)
        )
    )


def _order_text(order_agreement: float | None) -> str:
    return "n/a" if order_agreement is None else f"{order_agreement:.2f}"


def print_comparison(out: Console, comparison: Comparison) -> None:
    """Print the verdict and the numbers behind it."""
    a_in_b, b_in_a = comparison.contains
    table = Table(box=None, show_header=False, pad_edge=False)
    table.add_column(style=_LABEL)
    table.add_column()
    rows = (
        ("Verdict", comparison.verdict.value),
        ("Overlap", f"{comparison.overlap:.2f}"),
        ("A in B", f"{a_in_b:.2f}"),
        ("B in A", f"{b_in_a:.2f}"),
        ("Order agreement", _order_text(comparison.order_agreement)),
    )
    for label, value in rows:
        table.add_row(
            _text(label, _LABEL), _text(value, _TITLE if label == "Verdict" else _PLAIN)
        )
    out.print(table)


def _entry_label(reading_list: Mapping[str, Any], index: int) -> str:
    entry = (reading_list.get(ENTRIES_KEY) or ())[index]
    series = (entry.get(SERIES_KEY) or {}).get(NAME_KEY) or "?"
    return f"{index + 1} {series} #{entry_issue_name(entry)}"


def print_combine_report(
    out: Console, result: CombineResult, paths: Sequence[Path]
) -> None:
    """Print what each input added and every disagreement found."""
    reading_list = result.reading_list
    added = [0] * len(paths)
    for origins in result.provenance:
        added[origins[0].input_index] += 1
    for path, count in zip(paths, added, strict=True):
        noun = "entry" if count == 1 else "entries"
        out.print(
            Text.assemble(
                (printable(str(path)), _DIM), (f": {count} {noun} added", _PLAIN)
            )
        )
    for conflict in result.order_conflicts:
        message = (
            f"{_entry_label(reading_list, conflict.entry)}: {paths[conflict.input_index]}"
            f" puts it at row {conflict.row + 1}"
        )
        print_messages(out, (message,), "order")
    for conflict in result.id_conflicts:
        message = (
            f"{_entry_label(reading_list, conflict.entry)}: {conflict.source}"
            f" {conflict.kept} kept, {conflict.dropped} from"
            f" {paths[conflict.input_index]} row {conflict.row + 1}"
        )
        print_messages(out, (message,), "id")
    for index in result.name_joins:
        print_messages(out, (_entry_label(reading_list, index),), "joined by name only")
    for shared in result.shared_ids:
        positions = ", ".join(f"#{position + 1}" for position in shared.entries)
        message = f"{shared.source} {shared.key} is on entries {positions}"
        print_messages(out, (message,), "shared id")


def _results_table(columns: Sequence[str]) -> Table:
    table = Table(box=None, pad_edge=False)
    for column in columns:
        table.add_column(Text(column, style=_LABEL))
    return table


def print_metron_lists(out: Console, lists: "Sequence[MetronListSummary]") -> None:
    """Tabulate Metron search results; ``fetch metron:ID`` takes the ID."""
    table = _results_table(("ID", "Name", "Type", "Curator", "User", "Modified"))
    for found in lists:
        table.add_row(
            _text(found.id),
            _text(f"{found.name} (private)" if found.private else found.name),
            _text(found.list_type),
            _text(found.curator),
            _text(found.username, _DIM),
            _text(found.modified.date(), _DIM),
        )
    out.print(table)


def print_catalog_entries(out: Console, entries: "Sequence[CatalogEntry]") -> None:
    """Tabulate catalog search results; ``fetch catalog:PATH`` takes the path."""
    table = _results_table(("Curator", "Path"))
    for entry in entries:
        table.add_row(_text(entry.curator, _DIM), _text(entry.path))
    out.print(table)


def _shown_path(path: Path, directory: Path) -> str:
    """Show a comic's path under the directory searched, or whole when not."""
    try:
        return str(path.relative_to(directory))
    except ValueError:
        return str(path)


def print_matches(
    out: Console,
    reading_list: Mapping[str, Any],
    result: "MatchResult",
    directory: Path,
    notes: Mapping[Path, str] | None = None,
) -> None:
    """
    Tabulate a list's entries with the comics that are them, or missing.

    Each comic is a row of its own, with how it matched and its note. A
    cover-year match of one of several volumes is marked ambiguous. Under a
    missing entry, each comic refused for it as another volume or for its
    cover year is a row marked ``refused``.
    """
    notes = notes or {}
    found = {match.position: match for match in result.found}
    refused: dict[int, list[Refused]] = {}
    for refusal in result.refused:
        refused.setdefault(refusal.position, []).append(refusal)
    table = _results_table(("#", "Series", "Year/Vol", "Issue", "Comic", "By"))
    for position, entry in enumerate(reading_list.get(ENTRIES_KEY) or ()):
        cells = _entry_cells(position + 1, entry)[:4]
        if (match := found.get(position)) is None:
            table.add_row(*cells, _text("missing", _WARN), _text(""))
            for refusal in refused.get(position, ()):
                shown = _refused_cell(refusal, directory, notes.get(refusal.path))
                table.add_row(*[_text("")] * len(cells), shown, _text("refused", _DIM))
            continue
        for comic in match.comics:
            shown = _comic_cell(comic, directory, notes.get(comic.path), match)
            table.add_row(*cells, shown, _text(comic.by.value, _DIM))
            cells = [_text("")] * len(cells)
    out.print(table)


def _refused_cell(refusal: "Refused", directory: Path, note: str | None) -> Text:
    """Show a refused comic's path, its note, and why it was refused."""
    shown = Text(printable(_shown_path(refusal.path, directory)), style=_DIM)
    for text in (*([note] if note else []), refusal.reason.value):
        shown.append(f" ({printable(text)})", style=_WARN)
    return shown


def _comic_cell(
    comic: "FoundComic", directory: Path, note: str | None, match: "Found"
) -> Text:
    """Show a found comic's path, its note, and whether it is ambiguous."""
    shown = Text(printable(_shown_path(comic.path, directory)))
    notes = [note] if note else []
    if comic.ambiguous:
        notes.append(f"ambiguous: {volumes_text(match.volumes)}")
    for text in notes:
        shown.append(f" ({printable(text)})", style=_WARN)
    return shown


def _and(items: Sequence[str]) -> str:
    return ", ".join(items[:-1]) + f" and {items[-1]}" if len(items) > 1 else items[0]


def volumes_text(volumes: Sequence[int]) -> str:
    """
    Name the volumes an entry fits.

    By start year, ``the 2011 and 2016 volumes``, and by number,
    ``volumes 1 and 2``.
    """
    years = [str(value) for value in volumes if value >= YEAR_LIKE_VOLUME]
    numbers = [str(value) for value in volumes if value < YEAR_LIKE_VOLUME]
    parts = []
    if years:
        parts.append(f"the {_and(years)} volume{'s' if len(years) > 1 else ''}")
    if numbers:
        parts.append(f"volume{'s' if len(numbers) > 1 else ''} {_and(numbers)}")
    return " and ".join(parts)


_ARC_VERBS = MappingProxyType(
    {
        # (action, done): what the line says.
        ("add", False): "would add",
        ("add", True): "added",
        ("renumber", False): "would renumber",
        ("renumber", True): "renumbered",
    }
)


def arc_text(name: str, number: int | None) -> str:
    """Name an arc and its number, as a line about it shows them."""
    return f"{name!r}" if number is None else f"{name!r} #{number}"


def _dim_line(out: Console, path: Path | str, detail: str) -> None:
    out.print(
        Text.assemble((printable(str(path)), _DIM), (f": {printable(detail)}", _DIM))
    )


def _change_text(
    write: "ArcWrite", *, done: bool, moved: Path | None, deleted: bool
) -> str:
    change = write.change
    verb = _ARC_VERBS[change.action.value, done]
    detail = f"{verb} {arc_text(change.arc, change.number)}"
    if change.action.value == "renumber":
        had = "had no number" if change.current is None else f"was #{change.current}"
        detail += f", {had}"
    detail += _conversion_text(write, done=done, moved=moved, deleted=deleted)
    if write.removes:
        removes = "removed" if done else "would remove"
        detail += f"; {removes} {', '.join(write.removes)}"
    return detail


def _conversion_text(
    write: "ArcWrite", *, done: bool, moved: Path | None, deleted: bool
) -> str:
    """Say what converting a CBR, CBT or CB7 to a CBZ did, or would do."""
    kind = write.path.suffix[1:].upper()
    if done and moved is not None:
        return f" as {moved.name}" + (f"; deleted the {kind}" if deleted else "")
    if not done and write.converts_to is not None:
        then = "delete" if write.deletes_original else "keep"
        return f"; would convert to {write.converts_to.name} and {then} the {kind}"
    return ""


def _failed_line(out: Console, path: Path, detail: str) -> None:
    out.print(
        Text.assemble(
            Text("✗ ", style=_ERROR),
            (printable(str(path)), _PLAIN),
            (printable(f" {detail}"), _DIM),
        )
    )


def print_arc_write(
    out: Console,
    write: "ArcWrite",
    *,
    done: bool,
    problem: str | None = None,
    moved: Path | None = None,
    deleted: bool = False,
    removed: Mapping[Path, str | None] | None = None,
) -> None:
    """
    Print what tagging one file with an arc did, or would do, or why not.

    ``problem`` says why a write that was made did not hold, ``moved`` is
    the CBZ a write converted the file to, and ``deleted`` whether the
    original then went. The file's other paths follow, each on its own line,
    saying whether they went with it: ``removed`` gives each one removed,
    with why it could not be, if not.
    """
    change = write.change
    if change.action.value == "tagged":
        arc = arc_text(change.arc, change.number)
        _dim_line(out, change.path, f"already has {arc}; left alone")
    elif write.reason is not None:
        _failed_line(out, change.path, f"not written: {write.reason}")
    elif problem is not None:
        _failed_line(out, change.path, f"the write did not hold: {problem}")
    else:
        mark = Text("✓ ", style=_OK) if done else Text("· ", style=_DIM)
        out.print(
            Text.assemble(
                mark,
                (printable(str(change.path)), _PLAIN),
                (
                    printable(
                        " "
                        + _change_text(write, done=done, moved=moved, deleted=deleted)
                    ),
                    _DIM,
                ),
            )
        )
    _print_same_file(out, write, done=done, removed=removed or {})


def _print_same_file(
    out: Console, write: "ArcWrite", *, done: bool, removed: Mapping[Path, str | None]
) -> None:
    """List a file's other paths, and whether they go with a deleted original."""
    goes = not done and write.deletes_original and write.reason is None
    for other in write.same_file:
        detail = f"same file as {write.path}"
        if goes:
            detail += "; would be removed with it"
        elif other in removed:
            why = removed[other]
            detail += "; removed with it" if why is None else f"; not removed: {why}"
        _dim_line(out, other, detail)


def print_ambiguous(
    out: Console, path: Path, position: int, volumes: Sequence[int]
) -> None:
    """Say a comic is not tagged: its entry fits it and a comic of another volume."""
    kinds = []
    if any(value >= YEAR_LIKE_VOLUME for value in volumes):
        kinds.append("start year")
    if any(value < YEAR_LIKE_VOLUME for value in volumes):
        kinds.append("volume number")
    _failed_line(
        out,
        path,
        f"not written: entry #{position + 1} fits {volumes_text(volumes)}"
        f" alike; a {' or '.join(kinds)} on the entry settles it",
    )


def print_variant_only(out: Console, path: Path) -> None:
    """Say a comic was found only by a name variant, so is not tagged."""
    _dim_line(out, path, "found only by a name variant; --variants tags it")
