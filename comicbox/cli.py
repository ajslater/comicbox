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

from comicbox._pdf import PDF_ENABLED
from comicbox.box.online_lookup import OnlineLookupAbortedError
from comicbox.exceptions import UnsupportedArchiveTypeError
from comicbox.formats import MetadataFormats
from comicbox.print import PrintPhases
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
_PRINT_PHASES_DESC = MappingProxyType(
    {
        "v": ("Software version", "v"),
        "t": ("File type", ""),
        "f": ("File names", "l"),
        "s": ("Source metadata", ""),
        "l": ("Loaded metadata sources", ""),
        "n": ("Loaded metadata normalized to comicbox schema", ""),
        "m": ("Merged normalized intermediate metadata", ""),
        "c": ("Computed metadata sources", ""),
        "p": ("Final metadata merged with computed sources", "p"),
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
            "Particularly useful when paired with [cyan]-z[/cyan] to convert comic PDFs to CBZs "
            "without reencoding the images."
        ),
    }
)
_QUIET_LOGLEVEL = MappingProxyType({1: "INFO", 2: "SUCCESS", 3: "WARNING", 4: "ERROR"})

# Tracks one-shot stderr warnings so we don't spam users on repeated flag use.
_WARNED_FLAGS: set[str] = set()

# (policy, behavior on unambiguous top, on solo viable, on close call near top)
_MATCH_POLICY_ROWS = (
    ("always-prompt", "prompt", "prompt", "prompt"),
    ("strict", "auto-write", "prompt", "prompt"),
    ("normal (default)", "auto-write", "auto-write", "prompt"),
    ("eager", "auto-write", "auto-write", "auto-write"),
)
_MATCH_POLICY_UNATTENDED_NOTE = (
    "With [cyan]--unattended[/cyan]: every 'prompt' above becomes 'skip'. "
    "[yellow]always-prompt --unattended[/yellow] is rejected (no work)."
)

# (name, required credentials, accepted --id forms, website)
_ONLINE_SOURCES_INFO = (
    (
        "metron",
        "username + password",
        "metron:NNN",
        "https://metron.cloud",
    ),
    (
        "comicvine",
        "api_key",
        "comicvine:NNN  or  comicvine:4000-NNN",
        "https://comicvine.gamespot.com",
    ),
)
_MATCH_POLICY_INTRO = Styled(
    """
[bold]Online tagging — Match Resolution Policy[/bold]

Two knobs:

  [cyan]--policy <name>[/cyan]   how aggressively to auto-write a match:
                       [green]always-prompt[/green] · [green]strict[/green] · [green]normal[/green] (default) · [green]eager[/green]
  [cyan]--unattended[/cyan]      never prompt — turn 'prompt' decisions into 'skip'

Repeatable per source: [cyan]--policy metron:eager[/cyan]
[cyan]--confidence-threshold[/cyan] is also repeatable per source.

Each policy row below shows what happens to three kinds of candidate sets.
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
    """Parse page range."""

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
            namespace.index_from = index_from
        if index_to is not None:
            namespace.index_to = index_to


def _warn_once(key: str, message: str) -> None:
    if key in _WARNED_FLAGS:
        return
    _WARNED_FLAGS.add(key)
    sys.stderr.write(message + "\n")


class DeprecatedDryRunAction(Action):
    """Set dry_run=True with a deprecation warning. -y is gone in 5.0."""

    @override
    def __call__(
        self,
        parser: ArgumentParser,
        namespace: Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        _warn_once(
            "dry_run_y",
            "warning: -y is deprecated, use -n/--dry-run instead (removed in 5.0)",
        )
        namespace.dry_run = True


class ApiPasswordAction(Action):
    """Append --api-password values; warn that CLI passwords leak into shell history."""

    @override
    def __call__(
        self,
        parser: ArgumentParser,
        namespace: Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        _warn_once(
            "api_password",
            (
                "warning: --api-password leaks into shell history; "
                "prefer COMICBOX_<SOURCE>_PASSWORD env var or keyring"
            ),
        )
        items = list(getattr(namespace, self.dest, None) or [])
        if isinstance(values, str):
            items.append(values)
        elif isinstance(values, Sequence):
            items.extend(values)
        setattr(namespace, self.dest, items)


def _get_help_print_phases_table() -> Table:
    table = Table(title="[dark_cyan]PRINT_PHASE[/dark_cyan] characters", **_TABLE_ARGS)  # pyright: ignore[reportArgumentType], # ty: ignore[invalid-argument-type]
    table.add_column("Phase", style="green")
    table.add_column("Description")
    table.add_column("Shortcut", style="cyan")
    for phase, attrs in _PRINT_PHASES_DESC.items():
        desc, shortcut = attrs
        if shortcut:
            shortcut = "-" + shortcut
        table.add_row(phase, desc, shortcut)
    return table


def _get_pdf_page_format_phases_table() -> Table:
    table = Table(title="[dark_cyan]PDF_PAGE_FORMAT[/dark_cyan] values", **_TABLE_ARGS)  # pyright: ignore[reportArgumentType], # ty: ignore[invalid-argument-type]
    table.add_column("Value", style="green")
    table.add_column("Description")
    for key, desc in _PDF_PAGE_FORMAT_DESC.items():
        table.add_row(key, desc)
    return table


def _get_match_policy_table() -> Table:
    table = Table(
        title="[dark_cyan]Online — Match Resolution Policy[/dark_cyan]",
        **_TABLE_ARGS,  # pyright: ignore[reportArgumentType], # ty: ignore[invalid-argument-type]
    )
    table.add_column("--policy", style="green")
    # "Unambiguous" = top above threshold AND clear gap to runner-up.
    # "Solo viable" = exactly one candidate above min_confidence.
    # "Close call"  = top above threshold but runner-up close (gap < 0.10).
    table.add_column("unambiguous top")
    table.add_column("solo viable")
    table.add_column("close call")
    for row in _MATCH_POLICY_ROWS:
        table.add_row(*row)
    return table


def _get_online_sources_table() -> Table:
    table = Table(
        title=(
            "[dark_cyan]Online sources[/dark_cyan] for "
            "[cyan]--online[/cyan], [cyan]--id[/cyan], and "
            "[cyan]--api-*[/cyan]"
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


FORMAT_TITLE = """Format keys for [cyan]--ignore-read[/cyan], [cyan]--write[/cyan], and [cyan]--export[/cyan]\n
Formats shown in order of precedence. [dim]Dimmed[/dim] formats are not indented for distribution and are provided as convenience to developers."""


def _get_help_format_table() -> Table:
    table = Table(title=FORMAT_TITLE, **_TABLE_ARGS)  # pyright: ignore[reportArgumentType], # ty: ignore[invalid-argument-type]
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


def _add_online_options(option_group: Any) -> None:
    """Online metadata tagging flags."""
    option_group.add_argument(
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
    option_group.add_argument(
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
    option_group.add_argument(
        "--series-id",
        action="append",
        dest="explicit_series_ids",
        default=None,
        metavar="DB:ID",
        help=(
            "Constrain search to a specific series id from named source — "
            "skips the per-source series-discovery API call (saves up to "
            "[green]20[/green] requests). Filename-extracted issue number "
            "and year still apply. Implicitly enables online for that "
            "source. ComicVine accepts both [green]comicvine:NNN[/green] "
            "and [green]comicvine:4050-NNN[/green] (volume resource type)."
        ),
    )
    option_group.add_argument(
        "--policy",
        action="append",
        dest="policy",
        default=None,
        metavar="[DB:]NAME",
        help=(
            "Match-resolution policy: one of "
            "[green]always-prompt[/green], [green]strict[/green], "
            "[green]normal[/green] (default), [green]eager[/green]. "
            "Repeatable for per-source overrides "
            "([green]--policy metron:eager[/green])."
        ),
    )
    option_group.add_argument(
        "--unattended",
        dest="unattended",
        action="store_true",
        default=None,
        help=(
            "Never prompt. Decisions that would have prompted become "
            "[yellow]SKIP[/yellow]. Required for cron / batch runs."
        ),
    )
    option_group.add_argument(
        "--accept-only",
        dest="accept_only",
        action="store_true",
        default=None,
        help=(
            "[deprecated] Auto-accept solo matches. Translates to "
            "[green]--policy normal[/green]. Will be removed in a future "
            "release."
        ),
    )
    option_group.add_argument(
        "--skip-multiple",
        dest="skip_multiple",
        action="store_true",
        default=None,
        help=(
            "[deprecated] Skip files with >1 candidate. Translates to "
            "[green]--unattended --policy strict[/green]. Will be removed "
            "in a future release."
        ),
    )
    option_group.add_argument(
        "--ignore-existing",
        dest="ignore_existing",
        action="store_true",
        default=None,
        help="Skip files already tagged from this run's selected online sources.",
    )
    option_group.add_argument(
        "--tag-all-sources",
        dest="tag_all_sources",
        action="store_true",
        default=None,
        help=(
            "Query every configured online source instead of stopping after "
            "the first one that contributes data. Sources are tried in "
            "priority order ([green]metron[/green], then "
            "[green]comicvine[/green]); per-source [cyan]--id[/cyan] / "
            "[cyan]--series-id[/cyan] flags always run regardless."
        ),
    )
    option_group.add_argument(
        "--force-search",
        dest="force_search",
        action="store_true",
        default=None,
        help=(
            "Force a full search even if the comic has a stored identifier "
            "for the source. Use to override a stale or wrong stored id. "
            "Does not override an explicit [cyan]--id[/cyan] flag."
        ),
    )
    option_group.add_argument(
        "--confidence-threshold",
        action="append",
        dest="confidence_threshold",
        default=None,
        metavar="[DB:]FLOAT",
        help=(
            "Auto-write threshold (0-1). Repeatable for per-source "
            "overrides ([green]--confidence-threshold metron:0.75[/green])."
        ),
    )
    option_group.add_argument(
        "--api-budget",
        action="append",
        dest="api_budget",
        default=None,
        metavar="[DB:]MODE",
        help=(
            "API-call budget per comic: [green]exhaustive[/green], "
            "[green]balanced[/green] (default), [green]fast[/green]. "
            "Controls how aggressively pre-call algorithms trade "
            "accuracy for API throughput. Repeatable for per-source "
            "overrides ([green]--api-budget comicvine:fast[/green]). "
            "See `tasks/online-tagging/api-budget-user-doc.md`."
        ),
    )
    option_group.add_argument(
        "--cache-dir",
        dest="cache_dir",
        default=None,
        metavar="PATH",
        help="Override the on-disk cache directory for online responses.",
    )
    option_group.add_argument(
        "--cache-ttl",
        dest="cache_ttl",
        default=None,
        metavar="DURATION",
        help="Cache entry TTL ([green]7d[/green], [green]24h[/green], [green]60m[/green], [green]0[/green] for no expiry).",
    )
    option_group.add_argument(
        "--no-cache",
        dest="no_cache",
        action="store_true",
        default=False,
        help="Disable cache for this invocation (no read, no write).",
    )
    option_group.add_argument(
        "--refresh-cache",
        dest="refresh_cache",
        action="store_true",
        default=False,
        help="Skip cache reads but write fresh results back.",
    )
    option_group.add_argument(
        "--api-key",
        action="append",
        dest="api_keys",
        default=None,
        metavar="DB:KEY",
        help=(
            "Override API key for an api-key source "
            "(e.g. [green]--api-key comicvine:abcd1234[/green]). See the "
            "[cyan]Online sources[/cyan] table below for valid DB names."
        ),
    )
    option_group.add_argument(
        "--api-user",
        action="append",
        dest="api_users",
        default=None,
        metavar="DB:USER",
        help=(
            "Override username for a user-auth source. See the "
            "[cyan]Online sources[/cyan] table below for valid DB names."
        ),
    )
    option_group.add_argument(
        "--api-password",
        action=ApiPasswordAction,
        dest="api_passwords",
        default=None,
        metavar="DB:PASS",
        help=(
            "Override password for a user-auth source. Discouraged on the "
            "CLI (shell history); prefer env var or keyring."
        ),
    )
    option_group.add_argument(
        "--api-url",
        action="append",
        dest="api_urls",
        default=None,
        metavar="DB:URL",
        help=(
            "Override base URL for a source (e.g. self-hosted ComicVine mirror). "
            "Note: [yellow]metron[/yellow] is a no-op — mokkari's api() factory "
            "has no URL-override parameter. "
            "See the [cyan]Online sources[/cyan] table below for valid DB names."
        ),
    )
    option_group.add_argument(
        "-j",
        "--jobs",
        dest="jobs",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Parallel workers across files. Default [green]1[/green] (serial). "
            "[green]4[/green] is the recommended ceiling for cold-cache batch "
            "runs. [green]8[/green]+ is [yellow]not recommended for cold "
            "cache[/yellow] — under sustained API rate-limit contention with "
            "force-search or lowered thresholds, wall time can balloon 10x+ "
            "as workers patient-wait through the retry schedule (calibrated "
            "2026-05-15 at jobs=8: 5.7 hours vs 22 min at jobs=1 on the same "
            "fixture set). [green]16+[/green] is not faster than [green]8[/green]; "
            "both online libraries share a single rate-limit bucket per source."
        ),
    )


def _add_option_group(parser: ArgumentParser) -> None:
    option_group = parser.add_argument_group("Options")
    option_group.add_argument(
        "-c",
        "--config",
        metavar="CONFIG_PATH",
        action="store",
        help="Path to an alternate config file.",
    )
    option_group.add_argument(
        "-r",
        "--read",
        action=CSVAction,
        metavar="FORMATS",
        dest="read",
        help="Read metadata formats. Defaults to all.",
    )
    option_group.add_argument(
        "--read-ignore",
        action=CSVAction,
        metavar="FORMATS",
        dest="read_ignore",
        help="Subtract these formats from the read formats.",
    )
    option_group.add_argument(
        "-m",
        "--metadata",
        dest="metadata_cli",
        metavar="YAML_METADATA",
        action="append",
        help=(
            "Set metadata fields with linear YAML. (e.g.: [green]'keyA: value,"
            " keyB: [valueA,valueB,valueC], keyC: {subkey: {subsubkey: value}'[/green])"
            " Place a space after colons so they are properly parsed as YAML key"
            " value pairs. If your value contains a special YAML character (e.g."
            " :[]{}) quote the value. Linear YAML delineates subkeys with curly"
            " brackets in place of indentation."
        ),
    )
    option_group.add_argument(
        "-D",
        "--delete-keys",
        action=CSVAction,
        help=(
            "Delete a comma delimited list of comicbox glom key paths entirely from the final "
            "metadata. Example below."
        ),
    )
    option_group.add_argument(
        "-d",
        "--dest-path",
        help="destination path for extracting pages and metadata.",
    )
    option_group.add_argument(
        "--delete-orig",
        action="store_true",
        help="Delete the original cbr, cbt, or cb7 file if it was converted to a cbz successfully.",
    )
    option_group.add_argument(
        "--recurse",
        action="store_true",
        help="Perform selected actions recursively on a directory.",
    )
    option_group.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Do not write anything to the filesystem. Report on what would be done.",
    )
    option_group.add_argument(
        "-y",
        action=DeprecatedDryRunAction,
        nargs=0,
        dest="dry_run",
        default=False,
        help="[dim]Deprecated alias for [cyan]-n[/cyan]; removed in 5.0.[/dim]",
    )
    option_group.add_argument(
        "-g",
        "--compute-pages",
        dest="compute_pages",
        action="store_true",
        default=False,
        help=(
            "Compute the large ComicInfo style pages metadata from the archive. "
            "Turned off by default."
        ),
    )
    if PDF_ENABLED:
        option_group.add_argument(
            "-f",
            "--pdf-page-format",
            dest="pdf_page_format",
            action="store",
            default="",
            help="Method to extract pdf pages and covers. Valid values listed below.",
        )
    option_group.add_argument(
        "-A",
        "--no-compute-page-count",
        dest="compute_page_count",
        action="store_false",
        default=True,
        help=(
            "Do not compute the page count from the archive by reading the table of contents "
            "for image files."
        ),
    )
    option_group.add_argument(
        "-R",
        "--replace-metadata",
        action="store_true",
        default=False,
        help="Replace metadata keys instead of merging them.",
    )
    option_group.add_argument(
        "-Q",
        "--quiet",
        action="count",
        default=0,
        help=(
            "Increasingingly quiet success messages, warnings and errors with more Qs."
        ),
    )
    option_group.add_argument(
        "-s",
        "--stamp",
        dest="stamp",
        action="store_true",
        help=(
            "Normally comicbox will only update the notes (if enabled), tagger, and updated_at "
            "tags when performing a write or export action. This adds the stamps anyway."
        ),
    )
    option_group.add_argument(
        "-N",
        "--no-stamp-notes",
        dest="stamp_notes",
        action="store_false",
        help=(
            "Do not write the notes field with tagger, timestamp and identifiers "
            "when writing metadata out to a file."
        ),
    )
    option_group.add_argument(
        "-t",
        "--theme",
        help=(
            "Pygments theme to use for syntax highlighting. https://pygments.org/styles/. "
            "[green]'none'[/green] will stop highlighting."
        ),
    )
    _add_online_options(option_group)


def _add_action_group(parser: ArgumentParser) -> None:
    action_group = parser.add_argument_group("Actions")
    action_group.add_argument(
        "-P",
        "--print-phases",
        dest="print",
        metavar="PRINT_PHASES",
        action="store",
        default="",
        help=(
            "Print separate phases of metadata processing."
            " Specify with a string that contains phase characters"
            " listed below. e.g. -P [green]slcm[/green]."
        ),
    )
    action_group.add_argument(
        "-v",
        "--version",
        action="store_true",
        help="Print software version. Shortcut for -P [green]v[/green]",
    )
    action_group.add_argument(
        "-V",
        "--validate",
        dest="validate",
        action="store_true",
        help=(
            "Validate formats against schema if available. Schemas like ComicInfo enforce a "
            "strict tag order. Schemas available at "
            "https://github.com/ajslater/comicbox/tree/main/schemas"
        ),
    )
    action_group.add_argument(
        "-p",
        "--print",
        dest="print_metadata",
        action="store_true",
        help="Print merged metadata. Shortcut for -P [green]p[/green].",
    )
    action_group.add_argument(
        "-l",
        "--list",
        dest="print_filenames",
        action="store_true",
        help="Print filenames in archive. Shortcut for -P [green]f[/green].",
    )
    action_group.add_argument(
        "-i",
        "--import",
        action="append",
        dest="import_paths",
        help="Import metadata from external files. Accepts quoted globs.",
    )
    action_group.add_argument(
        "-x",
        "--export",
        metavar="FORMATS",
        action=CSVAction,
        help="Export metadata as external files to --dest-path. Format keys listed below.",
    )
    action_group.add_argument(
        "--delete-all-tags",
        action="store_true",
        help="Delete all tags from the archive. Overrides --write.",
    )
    action_group.add_argument(
        "-e",
        "--pages",
        action=PageRangeAction,
        help=(
            "Extract a single page or : delimited range of pages by zero based index"
            " to --dest-path."
        ),
    )
    action_group.add_argument(
        "-o", "--covers", action="store_true", help="Extract cover pages."
    )
    action_group.add_argument(
        "-z",
        "--cbz",
        action="store_true",
        help=(
            "Export the archive to CBZ format and rewrite all metadata formats found. "
            "When converting PDFs, by default a pixmap is taken of the page. Try -a [green]image[/green] "
            "if the PDF is a comic with only one big image per page."
        ),
    )
    action_group.add_argument(
        "-w",
        "--write",
        metavar="FORMATS",
        action=CSVAction,
        help=(
            "Write comic metadata formats to archive cbt & cbr files are always"
            " exported to a cbz file. Format keys listed below."
        ),
    )
    action_group.add_argument(
        "--rename",
        action="store_true",
        help="Rename the file with comicbox's filename format.",
    )
    action_group.add_argument(
        "-h", "--help", action="help", help="Show only this help message and exit"
    )


def _add_target_group(parser: ArgumentParser) -> None:
    target_group = parser.add_argument_group("Targets")
    target_group.add_argument(
        "paths",
        nargs="*",
        help="Paths to comic archives or directories",
    )


def get_args(params: Sequence[str] | None = None) -> Namespace:
    """Get arguments and options."""
    description = "Comic book archive multi format metadata read/write/transform tool and image extractor."
    if not PDF_ENABLED:
        description += "\n[yellow]Comicbox is not installed with PDF support.[/yellow]"

    epilog = Group(
        _get_help_print_phases_table(),
        _METADATA_EXAMPLES,
        _DELETE_KEYS_EXAMPLES,
        _get_online_sources_table(),
        _MATCH_POLICY_INTRO,
        _get_match_policy_table(),
        _get_help_format_table(),
        _get_pdf_page_format_phases_table(),
    )

    parser = ArgumentParser(
        description=description,
        epilog=epilog,  # pyright: ignore[reportArgumentType] # ty: ignore[invalid-argument-type]
        formatter_class=RichHelpFormatter,
        add_help=False,
    )
    _add_option_group(parser)
    _add_action_group(parser)
    _add_target_group(parser)

    if params is not None:
        params = params[1:]
    return parser.parse_args(params)


def post_process_args(cns: Namespace) -> None:
    """Adjust CLI config."""
    # Print options
    if cns.version:
        cns.print += PrintPhases.VERSION.value
    if cns.print_filenames:
        cns.print += PrintPhases.FILE_NAMES.value
    if cns.print_metadata:
        cns.print += PrintPhases.METADATA.value

    # Loglevel
    if cns.quiet:
        cns.loglevel = _QUIET_LOGLEVEL.get(cns.quiet, "CRITICAL")

    # --id is single-comic only; mass-tagging would mistag
    explicit_ids = getattr(cns, "explicit_ids", None) or ()
    paths = cns.paths or ()
    if explicit_ids and len(paths) > 1:
        sys.stderr.write("error: --id requires exactly one input path\n")
        sys.exit(2)


def main(params: Sequence[str] | None = None) -> None:
    """Get CLI arguments and perform the operation on the archive."""
    cns = get_args(params)
    post_process_args(cns)
    args = Namespace(comicbox=cns)

    runner = Runner(args)
    try:
        runner.run()
    except _HANDLED_EXCEPTIONS as exc:
        rich_print(f"[yellow]{exc}[/yellow]")
        sys.exit(1)
