"""Argparse layer for the comicbox CLI."""

import sys
from argparse import Action, ArgumentParser, Namespace
from collections.abc import Sequence
from typing import Any

from rich_argparse import RichHelpFormatter
from typing_extensions import override

from comicbox._pdf import PAGE_FORMAT_VALUES, PDF_ENABLED
from comicbox.cli.epilog import build_epilog

# Tracks one-shot stderr warnings so we don't spam users on repeated flag use.
_WARNED_FLAGS: set[str] = set()


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
            "to filter (e.g. [green]--online metron,comicvine[/green]). "
            "List order is run priority: the first source that matches "
            "wins unless [cyan]--all-sources[/cyan] is set. A durable "
            "order can be set via the [cyan]online.lookup.sources[/cyan] "
            "config key. See the [cyan]Online sources[/cyan] table below."
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
            "the first one that contributes data (overrides the "
            "[cyan]online.lookup.first_wins[/cyan] config key). Sources run "
            "in [cyan]--online[/cyan] / config-key order, defaulting to "
            "[green]metron[/green] then [green]comicvine[/green]; per-source "
            "[cyan]--id[/cyan] / [cyan]--series-id[/cyan] flags always run "
            "regardless."
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
            "Per-comic API effort for fan-out sources: [green]minimal[/green], "
            "[green]balanced[/green] (default), [green]thorough[/green]. Trades "
            "accuracy for fewer API calls on ComicVine; Metron doesn't fan out, so "
            "it ignores this. Per-source overrides via YAML only."
        ),
    )


def _add_target_group(parser: ArgumentParser) -> None:
    target_group = parser.add_argument_group("targets")
    target_group.add_argument(
        "paths",
        nargs="*",
        help="Paths to comic archives or directories.",
    )


def build_parser() -> ArgumentParser:
    """Assemble the full comicbox argument parser from the group builders."""
    description = "Comic book archive multi format metadata read/write/transform tool and image extractor."
    if not PDF_ENABLED:
        description += "\n[yellow]Comicbox is not installed with PDF support.[/yellow]"

    parser = ArgumentParser(
        description=description,
        epilog=build_epilog(),  # pyright: ignore[reportArgumentType] # ty: ignore[invalid-argument-type]
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
