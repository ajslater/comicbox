"""The online actions: search Metron or the catalog, and fetch a list."""

import sys
from argparse import ArgumentParser, ArgumentTypeError, Namespace
from collections.abc import Callable
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from rich_argparse import RichHelpFormatter

from comicbox.cli.parser import (
    add_online_auth_group,
    add_online_cache_group,
)
from comicbox.events import (
    Event,
    ReadingListFetchProgress,
    ReadingListFetchStarted,
)
from comicbox.exceptions import (
    ReadingListError,
)
from comicbox.readinglists.registry import (
    get_format,
)
from comicbox.readinglists.render import (
    print_catalog_entries,
    print_messages,
    print_metron_lists,
    print_note,
)
from comicbox.readinglists.serialize import (
    ReadingListResult,
)
from comicbox.readinglists.session import ReadingListSession

if sys.version_info >= (3, 12):
    from typing import override  # pyright: ignore[reportUnreachable]
else:
    from typing_extensions import override

if TYPE_CHECKING:
    from pathlib import Path

    from rich.console import Console

    from comicbox.config.settings import ComicboxSettings
from comicbox.readinglists.cli.run import (
    Run,
    add_write_options,
    cancellable,
    destination_problems,
)

_SETTING_DESTS = ("auth", "cache", "cache_dir", "cache_ttl", "general.config")
_URL_SCHEMES = frozenset({"http", "https"})
_URL_KIND = "url"
_METRON_KINDS = frozenset({"metron", "metron-arc"})
_CATALOG_KIND = "catalog"
_SEARCH_WHERE = ("metron", _CATALOG_KIND)


@dataclass(frozen=True, slots=True)
class FetchSpec:
    """What ``fetch`` was asked for: a source kind and its id, path or URL."""

    kind: str
    target: str

    @override
    def __str__(self) -> str:
        """Spell it as it was given, but a URL's user name and password."""
        if self.kind == _URL_KIND:
            from comicbox.readinglists.sources.url import without_userinfo

            return without_userinfo(self.target)
        return f"{self.kind}:{self.target}"


def fetch_spec(text: str) -> FetchSpec:
    """Parse ``metron:ID``, ``metron-arc:ID``, ``catalog:PATH`` or a URL."""
    if urlsplit(text).scheme.lower() in _URL_SCHEMES:
        return FetchSpec(_URL_KIND, text)
    kind, colon, target = text.partition(":")
    kind = kind.lower()
    # ASCII digits only: "²" is a digit to isdigit and not to int.
    if colon and kind in _METRON_KINDS and target.isascii() and target.isdigit():
        return FetchSpec(kind, target)
    if colon and kind == _CATALOG_KIND and target.strip():
        return FetchSpec(kind, target)
    reason = f"{text!r}: give metron:ID, metron-arc:ID, catalog:PATH or an http(s) URL"
    raise ArgumentTypeError(reason)


_Fetcher = Callable[[ReadingListSession, str], ReadingListResult | None]
_FETCHERS: MappingProxyType[str, _Fetcher] = MappingProxyType(
    {
        "metron": lambda session, target: session.fetch_metron_list(int(target)),
        "metron-arc": lambda session, target: session.fetch_metron_arc(int(target)),
        _CATALOG_KIND: lambda session, target: session.fetch_catalog(target),
        _URL_KIND: lambda session, target: session.fetch_url(target),
    }
)


def _settings(args: Namespace) -> "ComicboxSettings":
    """Build settings from the setting dests alone, as the doctor does."""
    from comicbox.config import get_config

    dests = {dest: getattr(args, dest, None) for dest in _SETTING_DESTS}
    return get_config(Namespace(comicbox=Namespace(**dests)))


class _Progress:
    """Say on stderr what a fetch is doing, unless told to be quiet."""

    def __init__(self, err: "Console", *, quiet: bool) -> None:
        self._err = err
        self._quiet = quiet

    def __call__(self, event: Event) -> None:
        """Print a fetch's start and each part that arrives."""
        if self._quiet:
            return
        if isinstance(event, ReadingListFetchStarted):
            print_note(self._err, f"Fetching {event.source} {event.key}...")
        elif isinstance(event, ReadingListFetchProgress) and event.index is not None:
            total = f" of {event.total:,}" if event.total is not None else ""
            print_note(self._err, f"  {event.index:,}{total} entries")


def open_session(run: Run) -> ReadingListSession:
    """Open a session on the command's settings, reporting progress."""
    from comicbox.version import set_user_agent_context

    set_user_agent_context("cli", client="readinglist")
    progress = _Progress(run.err, quiet=run.args.quiet > 0)
    return ReadingListSession(config=_settings(run.args), on_event=progress)


def _fetch(run: Run) -> None:
    spec: FetchSpec = run.args.spec
    fmt = get_format(run.args.to)
    output: Path | None = run.args.output
    if output and run.refuse(
        destination_problems([output], (), overwrite=run.args.overwrite)
    ):
        return
    with open_session(run) as session:
        fetcher = _FETCHERS[spec.kind]
        result = cancellable(run, session.cancel, lambda: fetcher(session, spec.target))
    if result is None:
        # Only a conditional fetch returns nothing, and the CLI makes none.
        run.fail(None, ReadingListError(f"{spec}: nothing was fetched"))
        return
    print_messages(run.err, result.warnings, f"{spec}: warning")
    run.write(result.reading_list, fmt, output)


def _search(run: Run) -> None:
    where: str = run.args.where
    query = " ".join(run.args.query)
    with open_session(run) as session:
        if where == _CATALOG_KIND:
            entries = cancellable(
                run, session.cancel, lambda: session.search_catalog(query)
            )
            if entries:
                print_catalog_entries(run.out, entries)
            found = len(entries)
        else:
            lists = cancellable(
                run, session.cancel, lambda: session.search_metron(name=query)
            )
            if lists:
                print_metron_lists(run.out, lists)
            found = len(lists)
    if not found:
        print_note(run.err, f"No {where} lists match {query!r}.")


def _add_online_options(parser: ArgumentParser) -> None:
    """Add the config file, auth and cache options the main parser has."""
    parser.add_argument(
        "-c",
        "--config",
        metavar="PATH",
        dest="general.config",
        help="A config file to read beside the usual ones.",
    )
    add_online_auth_group(parser)
    add_online_cache_group(parser)


def add_online_actions(actions: Any) -> None:
    """Add the online actions to the parser's subcommands."""
    sub = actions.add_parser(
        "search",
        help="Search Metron's reading lists or the DieselTech catalog.",
        description=(
            "Search Metron's reading lists by name (needs a Metron API token),"
            " or the paths of the DieselTech catalog on GitHub."
        ),
        formatter_class=RichHelpFormatter,
    )
    sub.add_argument(
        "where", choices=_SEARCH_WHERE, metavar="metron|catalog", help="Where to look."
    )
    sub.add_argument(
        "query", nargs="+", metavar="QUERY", help="Words the name or path holds."
    )
    _add_online_options(sub)
    sub = actions.add_parser(
        "fetch",
        help="Fetch a list from Metron, the catalog or a URL.",
        description=(
            "Fetch metron:ID (a Metron reading list), metron-arc:ID (a Metron"
            " story arc), catalog:PATH (a DieselTech list) or an http(s) URL,"
            " and write it, to stdout without -o. Metron needs an API token."
        ),
        formatter_class=RichHelpFormatter,
    )
    add_write_options(sub, "FILE", "Write here, not to stdout.")
    sub.add_argument(
        "spec",
        type=fetch_spec,
        metavar="WHAT",
        help="metron:ID, metron-arc:ID, catalog:PATH or an http(s) URL.",
    )
    _add_online_options(sub)


ACTIONS: MappingProxyType[str, Callable[[Run], None]] = MappingProxyType(
    {"search": _search, "fetch": _fetch}
)
