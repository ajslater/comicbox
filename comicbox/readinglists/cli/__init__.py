"""
``comicbox readinglist``, or ``comicbox rl``: work with reading lists.

Its own parser with real subcommands, not the main parser: that parser's
positionals are always comic archives and its option dests are tested
against the config template. Exits 0 on success, 1 when a reading-list,
file or network error stops it or any file fails, 2 for a usage error and
130 when a fetch is cancelled with Ctrl-C.

stdout carries only what was asked for, a list or a table; warnings,
losses, reports and log lines go to stderr. Nothing is written over an
input, and nothing over an existing file without ``--overwrite``.
"""

from argparse import ArgumentParser
from collections.abc import Callable, Sequence
from types import MappingProxyType

from confuse import ConfigError

from comicbox.cli.parser import RichArgumentParser
from comicbox.exceptions import (
    ConfigurationError,
    OnlineLookupAbortedError,
    ReadingListError,
)
from comicbox.readinglists.cli import comics, files, online
from comicbox.readinglists.cli.run import EXIT_CANCELLED, Run, write_text
from comicbox.readinglists.render import print_note

PROG = "comicbox readinglist"

_DESCRIPTION = """Read, convert, combine and compare reading lists, fetch
them from Metron, Comic Vine, the DieselTech catalog or a URL, and tag the
comics a list matches with its story arc.

Formats: ComicRack .cbl, json-cbl, and comicbox's own YAML and JSON.
`comicbox rl` is the short form. A comic file named readinglist or rl has
to be given to comicbox as ./readinglist or ./rl."""

_EPILOG = """Exits 1 when any file, fetch or comic fails, 2 for a usage
error, and 130 when Ctrl-C stops it."""

_ACTIONS: MappingProxyType[str, Callable[[Run], None]] = MappingProxyType(
    {**files.ACTIONS, **online.ACTIONS, **comics.ACTIONS}
)

__all__ = ("EXIT_CANCELLED", "PROG", "build_parser", "main", "write_text")


def build_parser() -> ArgumentParser:
    """Build the ``comicbox readinglist`` parser."""
    parser = RichArgumentParser(prog=PROG, description=_DESCRIPTION, epilog=_EPILOG)
    parser.add_argument(
        "-Q",
        "--quiet",
        action="count",
        default=0,
        help="Log less, as in a comicbox run.",
    )
    # prog given, argparse doesn't render this parser's usage to make the
    # actions' prog, which with rich help writes to stdout before any
    # action runs: an rl piped into a closed reader then failed at once.
    actions = parser.add_subparsers(
        dest="action", required=True, metavar="ACTION", prog=PROG
    )
    files.add_file_actions(actions)
    online.add_online_actions(actions)
    comics.add_comic_actions(actions)
    return parser


def main(params: Sequence[str]) -> int:
    """Run ``comicbox readinglist`` on the args after it; return the exit code."""
    from comicbox.logger import init_logging

    args = build_parser().parse_args(params)
    run = Run(args)
    init_logging(run.log_level, sink="stderr")
    try:
        _ACTIONS[args.action](run)
    except (OSError, ReadingListError, ConfigError, ConfigurationError) as exc:
        run.fail(None, exc)
        return 1
    except OnlineLookupAbortedError as exc:
        if not run.cancelled:
            # The gate's own abort, such as a spent daily quota.
            run.fail(None, exc)
            return 1
        print_note(run.err, "Cancelled.")
        return EXIT_CANCELLED
    except KeyboardInterrupt:
        print_note(run.err, "Cancelled.")
        return EXIT_CANCELLED
    return run.exit_code
