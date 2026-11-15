"""
Print reading lists, comparisons and combine reports for the CLI.

Every cell is a `Text` with a `Style`, never markup, and the consoles do
not highlight: series names and paths carry brackets (``[Marvel] Civil
War``) that markup would swallow or misread.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

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
from comicbox.readinglists.transform import entry_issue_name

_PLAIN = Style()
_TITLE = Style(bold=True)
_LABEL = Style(color="cyan")
_DIM = Style(dim=True)
_OK = Style(color="green")
_WARN = Style(color="yellow")
_ERROR = Style(color="red", bold=True)


def console(*, stderr: bool = False) -> Console:
    """Get a console that prints text as given."""
    return Console(highlight=False, stderr=stderr)


def _text(value: Any, style: Style = _PLAIN) -> Text:
    return Text("" if value is None else str(value), style=style)


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
    table = Table(
        title=_text(reading_list.get(NAME_KEY) or "(unnamed)", _TITLE),
        title_justify="left",
        box=None,
        show_header=False,
        pad_edge=False,
    )
    table.add_column(style=_LABEL)
    table.add_column()
    for label, value in _header_rows(reading_list):
        table.add_row(_text(label, _LABEL), _text(value))
    return table


def print_messages(out: Console, messages: Sequence[str], label: str) -> None:
    """Print warnings or losses, one per line."""
    for message in messages:
        out.print(Text.assemble((f"{label}: ", _WARN), (message, _PLAIN)))


def print_error(out: Console, path: Path | str | None, error: BaseException) -> None:
    """Print a failure without a traceback."""
    prefix = f"{path}: " if path else ""
    out.print(Text.assemble((prefix, _PLAIN), (str(error), _ERROR)))


def print_reading_list(out: Console, path: Path, result: ReadingListResult) -> None:
    """Print a list's header, entries and read warnings."""
    out.print(_text(f"{path} ({result.fmt.value.label})", _DIM))
    out.print(header_table(result.reading_list))
    out.print(entries_table(result.reading_list))
    print_messages(out, result.warnings, "warning")


def print_status(out: Console, path: Path | str, ok: bool, detail: str) -> None:  # noqa: FBT001
    """Print one line: a mark, the path and what was found."""
    mark = Text("✓ ", style=_OK) if ok else Text("✗ ", style=_ERROR)
    out.print(Text.assemble(mark, (str(path), _PLAIN), (f" {detail}", _DIM)))


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
        out.print(Text.assemble((str(path), _DIM), (f": {count} {noun} added", _PLAIN)))
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
