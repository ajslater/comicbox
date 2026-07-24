"""Rich help epilog presentation for the comicbox CLI."""

from types import MappingProxyType

from rich import box
from rich.console import Group
from rich.style import Style
from rich.styled import Styled
from rich.table import Table
from rich.text import Text

from comicbox._pdf import PAGE_FORMAT_VALUES
from comicbox.formats import FORMAT_REGISTRATIONS, MetadataFormats

_TABLE_ARGS = MappingProxyType(
    {
        "box": box.HEAVY,
        "border_style": "bright_black",
        "row_styles": ("", "on grey7"),
        "title_justify": "left",
    }
)

# (phase char, description, optional short flag alias)
_PRINT_PHASES_DESC = MappingProxyType(
    {
        "v": ("Software version", "-v"),
        "t": ("File type", ""),
        "f": ("File names", ""),
        "s": ("Source metadata", ""),
        "l": ("Loaded metadata sources", ""),
        "n": ("Loaded metadata normalized to comicbox schema", ""),
        "m": ("Merged normalized intermediate metadata", ""),
        "c": ("Computed metadata sources", ""),
        "p": ("Final metadata merged with computed sources", "-p"),
    }
)
_METADATA_EXAMPLES = Styled(
    """
Metadata can be any tag from any of the supported metadata formats.
Complex [cyan]--metadata[/cyan] Examples:
  [cyan]-m[/cyan] 'Character: anna,bea,carol, contributors: {inker: [Other Name], writer: [Other Name, Writer Name]}, arcs: {Arc Name: 1, Other Arc Name: 5}'
  [cyan]-m[/cyan] '{publisher: My Press}'
  [cyan]-m[/cyan] \"Title: 'GI Robot: Foreign and Domestic'\"
  [cyan]-m[/cyan] \"series: 'Solarpunk: Kūchū Bōsōzoku'\"
""",
    style="argparse.text",
)
_DELETE_KEYS_EXAMPLES = Styled(
    """
Glom key paths are dot delimited. Numbers are list indexes. This deletes three comma delimited nested key paths:

  [cyan]-D[/cyan] [green]series,arcs.Across the Multiverse.number,reprints.0.series[/green]
    """,
    style="argparse.text",
)
_PDF_PAGE_FORMAT_DESC = MappingProxyType(
    {
        "pdf": (
            "Extract pages as pdf (extraction default). A multi page "
            "[cyan]--extract-pages[/cyan] range is written as one pdf of the "
            "whole range."
        ),
        "pixmap": "Extract pages as an uncompressed pixmap of the page.",
        "image": (
            "Extract the first image on the page in its original unaltered format. "
            "Avoids reencoding when paired with [cyan]--cbz[/cyan], but pages whose "
            "displayed orientation is rotated are rendered to a jpeg instead so the "
            "output matches the display."
        ),
        "image_if_dominant": (
            "Extract the embedded image for pages that are mostly one image, "
            "in a browser renderable format. Pages with vector content fall "
            "back to pdf."
        ),
        "pixmap_jpeg": (
            "Rasterize the whole page to a jpeg. Always yields an image, for any "
            "page ([cyan]--cbz[/cyan] conversion default)."
        ),
    }
)

# (mode, behavior on unambiguous top, on solo viable, on close call near top)
_MATCH_MODE_ROWS = (
    ("ask", "prompt", "prompt", "prompt"),
    ("careful", "auto-write", "prompt", "prompt"),
    ("auto (default)", "auto-write", "auto-write", "prompt"),
    ("eager", "auto-write", "auto-write", "auto-write"),
)

# (name, required credentials, accepted --id forms, website) — derived
# from each online format's REGISTRATION.cli_info.
_ONLINE_SOURCES_INFO = tuple(
    (info.short_name, info.credentials, info.id_form, info.website)
    for registration in FORMAT_REGISTRATIONS.values()
    if (info := registration.cli_info) is not None
)
_MATCH_MODE_INTRO = Styled(
    """
[bold]Online tagging — Match Resolution[/bold]

Two knobs:

  [cyan]--match <mode>[/cyan]    how aggressively to auto-write a match:
                       [green]ask[/green] · [green]careful[/green] · [green]auto[/green] (default) · [green]eager[/green]
  [cyan]--prompts never[/cyan]   never prompt — turn 'prompt' decisions into 'skip'

Each mode row below shows what happens to three kinds of candidate sets.
""",
    style="argparse.text",
)


def _get_help_print_phases_table() -> Table:
    table = Table(
        title="[dark_cyan]--print PHASES[/dark_cyan] characters",
        **_TABLE_ARGS,  # pyright: ignore[reportArgumentType], # ty: ignore[invalid-argument-type]
    )
    table.add_column("Phase", style="green")
    table.add_column("Description")
    table.add_column("Alias", style="cyan")
    for phase, attrs in _PRINT_PHASES_DESC.items():
        desc, shortcut = attrs
        table.add_row(phase, desc, shortcut)
    return table


def _get_pdf_page_format_phases_table() -> Table:
    table = Table(
        title="[dark_cyan]--pdf-pages[/dark_cyan] values",
        **_TABLE_ARGS,  # pyright: ignore[reportArgumentType], # ty: ignore[invalid-argument-type]
    )
    table.add_column("Value", style="green")
    table.add_column("Description")
    # Rows come from the installed pdffile so they always match the values
    # argparse accepts.
    for value in PAGE_FORMAT_VALUES:
        table.add_row(value, _PDF_PAGE_FORMAT_DESC.get(value, ""))
    return table


def _get_match_mode_table() -> Table:
    table = Table(
        title="[dark_cyan]Online — Match Resolution[/dark_cyan]",
        **_TABLE_ARGS,  # pyright: ignore[reportArgumentType], # ty: ignore[invalid-argument-type]
    )
    table.add_column("--match", style="green")
    # "Unambiguous" = top above threshold AND clear gap to runner-up.
    # "Solo viable" = exactly one candidate above min_confidence.
    # "Close call"  = top above threshold but runner-up close (gap < 0.10).
    table.add_column("unambiguous top")
    table.add_column("solo viable")
    table.add_column("close call")
    for row in _MATCH_MODE_ROWS:
        table.add_row(*row)
    return table


def _get_online_sources_table() -> Table:
    table = Table(
        title=(
            "[dark_cyan]Online sources[/dark_cyan] for "
            "[cyan]--online[/cyan], [cyan]--id[/cyan], and "
            "[cyan]--auth[/cyan]"
        ),
        **_TABLE_ARGS,  # pyright: ignore[reportArgumentType], # ty: ignore[invalid-argument-type]
    )
    table.add_column("Source", style="green")
    table.add_column("Required credentials")
    table.add_column("--id form")
    table.add_column("Website")
    for row in _ONLINE_SOURCES_INFO:
        table.add_row(*row)
    return table


_FORMAT_TABLE_TITLE = """Format keys for [cyan]--read[/cyan], [cyan]--read-except[/cyan], [cyan]--write[/cyan], and [cyan]--export[/cyan]\n
Formats shown in order of precedence. [dim]Dimmed[/dim] formats are not intended for distribution and are provided as convenience to developers."""


def _get_help_format_table() -> Table:
    table = Table(title=_FORMAT_TABLE_TITLE, **_TABLE_ARGS)  # pyright: ignore[reportArgumentType], # ty: ignore[invalid-argument-type]
    table.add_column("Format")
    table.add_column("Keys", style="green")
    for fmt in reversed(MetadataFormats):
        if not fmt.value.enabled:
            continue
        label = fmt.value.label
        if label.startswith("Comicbox"):
            style = Style(dim=True)
            label = Text(label, style=style)
        keys = ", ".join(sorted(fmt.value.config_keys))
        table.add_row(label, keys)

    return table


def build_epilog() -> Group:
    """Assemble the rich epilog rendered below the argparse help."""
    renderables = [
        _get_help_print_phases_table(),
        _METADATA_EXAMPLES,
        _DELETE_KEYS_EXAMPLES,
        _get_online_sources_table(),
        _MATCH_MODE_INTRO,
        _get_match_mode_table(),
        _get_help_format_table(),
    ]
    # Without pdffile installed there is no --pdf-pages option to document.
    if PAGE_FORMAT_VALUES:
        renderables.append(_get_pdf_page_format_phases_table())
    return Group(*renderables)
