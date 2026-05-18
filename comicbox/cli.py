"""Cli for comicbox."""

import sys
from argparse import Action, ArgumentParser, Namespace
from collections.abc import Sequence
from types import MappingProxyType
from typing import Any

from rich import box
from rich import print as rich_print
from rich.console import Group
from rich.style import Style
from rich.styled import Styled
from rich.table import Table
from rich.text import Text
from rich_argparse import RichHelpFormatter
from typing_extensions import override

from comicbox._pdf import PAGE_FORMAT_VALUES, PDF_ENABLED
from comicbox.box.online_lookup import OnlineLookupAbortedError
from comicbox.exceptions import UnsupportedArchiveTypeError
from comicbox.formats import FORMAT_REGISTRATIONS, MetadataFormats
from comicbox.run import Runner

_TABLE_ARGS = MappingProxyType(
    {
        "box": box.HEAVY,
        "border_style": "bright_black",
        "row_styles": ("", "on grey7"),
        "title_justify": "left",
    }
)
_HANDLED_EXCEPTIONS = (UnsupportedArchiveTypeError, OnlineLookupAbortedError)

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
        "pdf": "Extract pages as pdf file of one page.",
        "pixmap": "Extract pages as an uncompressed pixmap of the page.",
        "image": (
            "Extract the first image in it's original unaltered format on the page. "
            "Particularly useful when paired with [cyan]--cbz[/cyan] to convert comic PDFs to CBZs "
            "without reencoding the images."
        ),
    }
)
_QUIET_LOGLEVEL = MappingProxyType({1: "INFO", 2: "SUCCESS", 3: "WARNING", 4: "ERROR"})

# Tracks one-shot stderr warnings so we don't spam users on repeated flag use.
_WARNED_FLAGS: set[str] = set()

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


class CSVAction(Action):
    """Parse comma delimited sequences."""

    @override
    def __call__(
        self,
        parser: ArgumentParser,
        namespace: Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        """Parse comma delimited sequences."""
        if isinstance(values, str):
            values_array = [v.strip() for v in values.split(",") if v.strip()]
        elif isinstance(values, Sequence):
            values_array = list(values)
        else:
            return
        setattr(namespace, self.dest, values_array)


class PageRangeAction(Action):
    """Parse page range delimited by ``:``."""

    @override
    def __call__(
        self,
        parser: ArgumentParser,
        namespace: Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        """Parse page range delimited by :."""
        if isinstance(values, str):
            values = values.split(":")
        if not values:
            return

        index_from = int(values[0]) if len(values[0]) else None

        if len(values) == 1:
            index_to = index_from
        elif len(values[1]):
            index_to = int(values[1])
        else:
            index_to = None

        if index_from is not None:
            namespace.extract_pages_from = index_from
        if index_to is not None:
            namespace.extract_pages_to = index_to


def _warn_once(key: str, message: str) -> None:
    if key in _WARNED_FLAGS:
        return
    _WARNED_FLAGS.add(key)
    sys.stderr.write(message + "\n")


class AuthAction(Action):
    """
    Append ``--auth`` values; warn when a ``pass`` field leaks into shell history.

    Validates syntax lightly here (presence of ``:`` and ``=``); deeper
    validation (known source / known field) happens in
    ``CliOverrides.from_auth_list`` so callers using the API see the
    same error surface.
    """

    @override
    def __call__(
        self,
        parser: ArgumentParser,
        namespace: Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        items = list(getattr(namespace, self.dest, None) or [])
        raw_entries: list[str] = []
        if isinstance(values, str):
            raw_entries.append(values)
        elif isinstance(values, Sequence):
            raw_entries.extend(values)
        for raw in raw_entries:
            head, _, _ = raw.partition("=")
            _, _, cred_field = head.partition(":")
            if cred_field.strip().lower() == "pass":
                _warn_once(
                    "auth_pass",
                    (
                        "warning: --auth <source>:pass=... leaks into shell history; "
                        "prefer COMICBOX_<SOURCE>_PASS env var or keyring"
                    ),
                )
            items.append(raw)
        setattr(namespace, self.dest, items)


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
    for key, desc in _PDF_PAGE_FORMAT_DESC.items():
        table.add_row(key, desc)
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


def _add_general_group(parser: ArgumentParser) -> None:
    group = parser.add_argument_group("general")
    group.add_argument(
        "-c",
        "--config",
        metavar="PATH",
        action="store",
        default=None,
        dest="general_config",
        help="Path to an alternate config file.",
    )
    group.add_argument(
        "-r",
        "--recurse",
        action="store_true",
        default=None,
        dest="general_recurse",
        help="Perform selected actions recursively on directory arguments.",
    )
    group.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        default=None,
        dest="general_dry_run",
        help="Do not write anything to the filesystem. Report on what would be done.",
    )
    group.add_argument(
        "-Q",
        "--quiet",
        action="count",
        default=None,
        dest="general_quiet",
        help=(
            "Increasingly quiet success messages, warnings, and errors with more Qs."
        ),
    )
    group.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=None,
        metavar="N",
        dest="general_jobs",
        help=(
            "Parallel workers across files. Default [green]1[/green] (serial). "
            "[green]4[/green] is the recommended ceiling for cold-cache batch runs."
        ),
    )
    group.add_argument(
        "-d",
        "--dest-path",
        default=None,
        dest="general_dest_path",
        help="Destination path for extracting pages and metadata.",
    )
    group.add_argument(
        "-m",
        "--metadata",
        action="append",
        default=None,
        metavar="YAML",
        dest="general_metadata_cli",
        help=(
            "Set metadata fields with linear YAML. (e.g.: [green]'keyA: value,"
            " keyB: [valueA,valueB,valueC], keyC: {subkey: {subsubkey: value}'[/green])"
            " Place a space after colons so they are properly parsed as YAML key"
            " value pairs. If your value contains a special YAML character (e.g."
            " :[]{}) quote the value. Linear YAML delineates subkeys with curly"
            " brackets in place of indentation. Repeatable."
        ),
    )
    group.add_argument(
        "-D",
        "--delete-keys",
        action=CSVAction,
        default=None,
        dest="general_delete_keys",
        help=(
            "Delete a comma delimited list of comicbox glom key paths entirely from the final "
            "metadata. Example below."
        ),
    )
    group.add_argument(
        "--delete-orig",
        action="store_true",
        default=None,
        dest="general_delete_orig",
        help="Delete the original cbr, cbt, or cb7 file if it was converted to a cbz successfully.",
    )


def _add_read_group(parser: ArgumentParser) -> None:
    group = parser.add_argument_group("read")
    group.add_argument(
        "--read",
        action=CSVAction,
        metavar="FORMATS",
        default=None,
        dest="read_formats",
        help="Metadata formats to read. Defaults to all. Keys listed below.",
    )
    group.add_argument(
        "--read-except",
        action=CSVAction,
        metavar="FORMATS",
        default=None,
        dest="read_except",
        help="Subtract these formats from the read formats.",
    )


def _add_write_group(parser: ArgumentParser) -> None:
    group = parser.add_argument_group("write")
    group.add_argument(
        "-w",
        "--write",
        action=CSVAction,
        metavar="FORMATS",
        default=None,
        dest="write_formats",
        help=(
            "Write comic metadata formats back to the archive. cbt and cbr files are always"
            " exported to a cbz file. Format keys listed below."
        ),
    )
    group.add_argument(
        "--replace",
        action="store_true",
        default=None,
        dest="write_replace",
        help="Replace metadata keys instead of merging them.",
    )
    group.add_argument(
        "--stamp",
        action="store_true",
        default=None,
        dest="write_stamp",
        help=(
            "Normally comicbox only updates the notes (if enabled), tagger, and updated_at "
            "tags when performing a write or export action. This adds the stamps anyway."
        ),
    )
    group.add_argument(
        "--no-stamp-notes",
        action="store_false",
        default=None,
        dest="write_stamp_notes",
        help=(
            "Do not write the notes field with tagger, timestamp and identifiers "
            "when writing metadata out to a file."
        ),
    )
    group.add_argument(
        "--delete-all-tags",
        action="store_true",
        default=None,
        dest="write_delete_all_tags",
        help="Delete all tags from the archive. Overrides --write.",
    )


def _add_print_group(parser: ArgumentParser) -> None:
    group = parser.add_argument_group("print")
    group.add_argument(
        "--print",
        action="store",
        default=None,
        metavar="PHASES",
        dest="print_phases",
        help=(
            "Print one or more phases of metadata processing. Pass a string of phase"
            " characters listed below (e.g. [green]slcm[/green])."
        ),
    )
    group.add_argument(
        "-p",
        action="store_true",
        default=None,
        dest="print_metadata",
        help="Print merged metadata. Shortcut for [green]--print p[/green].",
    )
    group.add_argument(
        "-v",
        "--version",
        action="store_true",
        default=None,
        dest="print_version",
        help="Print software version. Shortcut for [green]--print v[/green].",
    )
    group.add_argument(
        "--validate",
        action="store_true",
        default=None,
        dest="print_validate",
        help=(
            "Validate formats against schema if available. Schemas like ComicInfo enforce a "
            "strict tag order. Schemas available at "
            "https://github.com/ajslater/comicbox/tree/main/schemas"
        ),
    )


def _add_convert_group(parser: ArgumentParser) -> None:
    group = parser.add_argument_group("convert")
    group.add_argument(
        "--cbz",
        action="store_true",
        default=None,
        dest="convert_cbz",
        help=(
            "Export the archive to CBZ format and rewrite all metadata formats found. "
            "When converting PDFs, by default a pixmap is taken of the page. "
            "Try [cyan]--pdf-pages image[/cyan] if the PDF is a comic with only one big "
            "image per page."
        ),
    )
    group.add_argument(
        "--rename",
        action="store_true",
        default=None,
        dest="convert_rename",
        help="Rename the file with comicbox's filename format.",
    )
    group.add_argument(
        "--extract-pages",
        action=PageRangeAction,
        default=None,
        metavar="RANGE",
        dest="extract_pages",
        help=(
            "Extract a single page or [green]:[/green] delimited range of pages by zero based"
            " index to --dest-path."
        ),
    )
    group.add_argument(
        "--extract-covers",
        action="store_true",
        default=None,
        dest="convert_extract_covers",
        help="Extract cover pages.",
    )
    group.add_argument(
        "--import",
        action="append",
        default=None,
        metavar="PATH",
        dest="convert_import_paths",
        help="Import metadata from external files. Accepts quoted globs. Repeatable.",
    )
    group.add_argument(
        "--export",
        action=CSVAction,
        default=None,
        metavar="FORMATS",
        dest="convert_export_formats",
        help="Export metadata as external files to --dest-path. Format keys listed below.",
    )
    if PDF_ENABLED:
        group.add_argument(
            "--pdf-pages",
            action="store",
            default=None,
            choices=PAGE_FORMAT_VALUES,
            metavar="MODE",
            dest="convert_pdf_pages",
            help="Method to extract pdf pages and covers. Valid values listed below.",
        )


def _add_online_lookup_group(parser: ArgumentParser) -> None:
    group = parser.add_argument_group("online: lookup")
    group.add_argument(
        "--online",
        action=CSVAction,
        dest="online_sources",
        default=None,
        metavar="SOURCES",
        help=(
            "Enable online metadata lookup. Pass [green]all[/green] to use "
            "every configured source, or a comma-separated list of sources "
            "to filter (e.g. [green]--online metron,comicvine[/green]). See "
            "the [cyan]Online sources[/cyan] table below."
        ),
    )
    group.add_argument(
        "--id",
        action="append",
        dest="explicit_ids",
        default=None,
        metavar="DB:ID",
        help=(
            "Skip search; tag by exact issue id from named source. "
            "Implicitly enables online for that source. "
            "ComicVine accepts both [green]comicvine:NNN[/green] and "
            "[green]comicvine:4000-NNN[/green]. Repeatable for cross-source "
            "confirmation (first non-error wins). Errors out if more than "
            "one input comic is submitted. Sources listed in the "
            "[cyan]Online sources[/cyan] table below."
        ),
    )
    group.add_argument(
        "--series-id",
        action="append",
        dest="explicit_series_ids",
        default=None,
        metavar="DB:ID",
        help=(
            "Constrain search to a specific series id from named source — "
            "skips the per-source series-discovery API call. "
            "Filename-extracted issue number and year still apply. "
            "Implicitly enables online for that source. "
            "ComicVine accepts both [green]comicvine:NNN[/green] "
            "and [green]comicvine:4050-NNN[/green] (volume resource type)."
        ),
    )
    group.add_argument(
        "--match",
        action="store",
        default=None,
        choices=("ask", "careful", "auto", "eager"),
        metavar="MODE",
        dest="match",
        help=(
            "Match-resolution aggressiveness: one of "
            "[green]ask[/green], [green]careful[/green], "
            "[green]auto[/green] (default), [green]eager[/green]. "
            "See the [cyan]Match Resolution[/cyan] table below."
        ),
    )
    group.add_argument(
        "--prompts",
        action="store",
        default=None,
        choices=("ask", "never"),
        metavar="MODE",
        dest="prompts",
        help=(
            "Whether comicbox may prompt mid-run. "
            "[green]ask[/green] (default) or [green]never[/green] "
            "(turn 'prompt' decisions into 'skip' — required for cron / batch runs)."
        ),
    )
    group.add_argument(
        "--rematch",
        action="store_true",
        default=None,
        dest="rematch",
        help=(
            "Force a fresh search even if the comic has a stored upstream id, "
            "ignoring the fast stored-id refresh path."
        ),
    )
    group.add_argument(
        "--all-sources",
        action="store_true",
        default=None,
        dest="all_sources",
        help=(
            "Query every configured online source instead of stopping after "
            "the first one that contributes data. Sources are tried in "
            "priority order ([green]metron[/green], then "
            "[green]comicvine[/green]); per-source [cyan]--id[/cyan] / "
            "[cyan]--series-id[/cyan] flags always run regardless."
        ),
    )


def _add_online_auth_group(parser: ArgumentParser) -> None:
    group = parser.add_argument_group("online: auth")
    group.add_argument(
        "--auth",
        action=AuthAction,
        default=None,
        metavar="SRC:FIELD=VAL",
        dest="auth",
        help=(
            "Per-source credentials. Repeatable. "
            "Valid fields: [green]user[/green], [green]pass[/green], "
            "[green]key[/green], [green]url[/green]. "
            "Examples: [green]--auth metron:user=NAME[/green], "
            "[green]--auth metron:pass=PASS[/green] (warns: leaks into shell history), "
            "[green]--auth comicvine:key=KEY[/green]. "
            "Prefer the [cyan]COMICBOX_<SOURCE>_<FIELD>[/cyan] env vars where possible."
        ),
    )


def _add_online_cache_group(parser: ArgumentParser) -> None:
    group = parser.add_argument_group("online: cache")
    group.add_argument(
        "--cache",
        action="store",
        default=None,
        choices=("on", "off", "refresh"),
        metavar="MODE",
        dest="cache",
        help=(
            "Cache mode for online responses: "
            "[green]on[/green] (default), [green]off[/green] (no read or write), "
            "[green]refresh[/green] (skip reads, write fresh results)."
        ),
    )
    group.add_argument(
        "--cache-dir",
        default=None,
        metavar="PATH",
        dest="cache_dir",
        help="Override the on-disk cache directory for online responses.",
    )
    group.add_argument(
        "--cache-ttl",
        default=None,
        metavar="DURATION",
        dest="cache_ttl",
        help=(
            "Cache entry TTL ([green]7d[/green], [green]24h[/green], [green]60m[/green],"
            " [green]0[/green] for no expiry)."
        ),
    )


def _add_online_tuning_group(parser: ArgumentParser) -> None:
    group = parser.add_argument_group("online: tuning")
    group.add_argument(
        "--auto-threshold",
        default=None,
        type=float,
        metavar="FLOAT",
        dest="auto_threshold",
        help=(
            "Global auto-write threshold in [green][0, 1][/green]. Default "
            "[green]0.95[/green]. Per-source overrides via YAML only."
        ),
    )
    group.add_argument(
        "--effort",
        action="store",
        default=None,
        choices=("minimal", "balanced", "thorough"),
        metavar="MODE",
        dest="effort",
        help=(
            "Per-comic API effort: [green]minimal[/green], [green]balanced[/green] "
            "(default), [green]thorough[/green]. Controls how aggressively pre-call "
            "algorithms trade accuracy for API throughput. Per-source overrides via YAML only."
        ),
    )


def _add_target_group(parser: ArgumentParser) -> None:
    target_group = parser.add_argument_group("targets")
    target_group.add_argument(
        "paths",
        nargs="*",
        help="Paths to comic archives or directories.",
    )


def _build_parser() -> ArgumentParser:
    description = "Comic book archive multi format metadata read/write/transform tool and image extractor."
    if not PDF_ENABLED:
        description += "\n[yellow]Comicbox is not installed with PDF support.[/yellow]"

    epilog = Group(
        _get_help_print_phases_table(),
        _METADATA_EXAMPLES,
        _DELETE_KEYS_EXAMPLES,
        _get_online_sources_table(),
        _MATCH_MODE_INTRO,
        _get_match_mode_table(),
        _get_help_format_table(),
        _get_pdf_page_format_phases_table(),
    )

    parser = ArgumentParser(
        description=description,
        epilog=epilog,  # pyright: ignore[reportArgumentType] # ty: ignore[invalid-argument-type]
        formatter_class=RichHelpFormatter,
        add_help=False,
    )
    _add_general_group(parser)
    _add_read_group(parser)
    _add_write_group(parser)
    _add_print_group(parser)
    _add_convert_group(parser)
    _add_online_lookup_group(parser)
    _add_online_auth_group(parser)
    _add_online_cache_group(parser)
    _add_online_tuning_group(parser)
    _add_target_group(parser)
    parser.add_argument(
        "-h", "--help", action="help", help="Show this help message and exit."
    )
    return parser


def _drain_attrs(cns: Namespace, prefix: str) -> dict[str, Any]:
    """Pop and return all flat attrs on ``cns`` whose names start with ``prefix``."""
    out: dict[str, Any] = {}
    for attr in [a for a in vars(cns) if a.startswith(prefix)]:
        value = getattr(cns, attr)
        delattr(cns, attr)
        if value is None:
            continue
        out[attr.removeprefix(prefix)] = value
    return out


def _build_nested(cns: Namespace, prefix: str) -> Namespace:
    """Drain prefix-keyed flat attrs into a nested Namespace."""
    return Namespace(**_drain_attrs(cns, prefix))


def _reshape_print(cns: Namespace) -> None:
    """Fold the three print convenience flags into ``print.phases``."""
    raw_phases: str = getattr(cns, "print_phases", None) or ""
    if getattr(cns, "print_version", None):
        raw_phases += "v"
    if getattr(cns, "print_metadata", None):
        raw_phases += "p"
    validate = getattr(cns, "print_validate", None)
    for attr in ("print_phases", "print_metadata", "print_version", "print_validate"):
        if hasattr(cns, attr):
            delattr(cns, attr)
    nested = Namespace()
    if raw_phases:
        nested.phases = raw_phases
    if validate is not None:
        nested.validate = validate
    cns.print = nested


def _reshape_read(cns: Namespace) -> None:
    """``--read``/``--read-except`` → ``cns.read`` Namespace."""
    formats = getattr(cns, "read_formats", None)
    except_ = getattr(cns, "read_except", None)
    for attr in ("read_formats", "read_except"):
        if hasattr(cns, attr):
            delattr(cns, attr)
    nested = Namespace()
    if formats is not None:
        nested.formats = formats
    if except_ is not None:
        # YAML key is ``except`` (reserved word in Python — set via setattr).
        setattr(nested, "except", except_)
    cns.read = nested


def _reshape_convert(cns: Namespace) -> None:
    """Convert nested namespace + page-range expansion."""
    nested = _build_nested(cns, "convert_")
    # PageRangeAction wrote to flat extract_pages_from / extract_pages_to.
    for attr in ("extract_pages_from", "extract_pages_to", "extract_pages"):
        if (val := getattr(cns, attr, None)) is not None and attr != "extract_pages":
            setattr(nested, attr, val)
        if hasattr(cns, attr):
            delattr(cns, attr)
    cns.convert = nested


def post_process_args(cns: Namespace) -> None:
    """
    Reshape the flat argparse namespace into the nested config shape.

    The new config tree (``general / read / write / print / convert /
    compute / online``) lives under ``cns.<group>.*`` so confuse's
    ``set_args`` overlays each CLI value at the matching YAML path.

    Online runtime fields (``--online``, ``--id``, ``--match``, ...)
    stay flat at the top of ``cns`` — they're consumed by
    ``_runtime_online_inputs`` / ``_build_online_settings`` directly,
    not via confuse layering.
    """
    # --id is single-comic only; mass-tagging would mistag.
    explicit_ids = getattr(cns, "explicit_ids", None) or ()
    paths = cns.paths or ()
    if explicit_ids and len(paths) > 1:
        sys.stderr.write("error: --id requires exactly one input path\n")
        sys.exit(2)

    # General — fold -Q into loglevel.
    quiet = getattr(cns, "general_quiet", None)
    if hasattr(cns, "general_quiet"):
        delattr(cns, "general_quiet")
    general = _build_nested(cns, "general_")
    if quiet is not None and quiet > 0:
        general.loglevel = _QUIET_LOGLEVEL.get(quiet, "CRITICAL")
    cns.general = general

    _reshape_read(cns)

    cns.write = _build_nested(cns, "write_")
    _reshape_print(cns)
    _reshape_convert(cns)


def get_args(params: Sequence[str] | None = None) -> Namespace:
    """Parse CLI arguments and reshape into the nested config namespace."""
    parser = _build_parser()
    if params is not None:
        params = params[1:]
    cns = parser.parse_args(params)
    post_process_args(cns)
    return cns


def main(params: Sequence[str] | None = None) -> None:
    """Get CLI arguments and perform the operation on the archive."""
    cns = get_args(params)
    args = Namespace(comicbox=cns)

    runner = Runner(args)
    try:
        runner.run()
    except _HANDLED_EXCEPTIONS as exc:
        rich_print(f"[yellow]{exc}[/yellow]")
        sys.exit(1)
