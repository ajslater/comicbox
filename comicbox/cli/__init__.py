"""Cli for comicbox."""

import sys
from argparse import Namespace
from collections.abc import Sequence

from confuse import ConfigError
from rich import print as rich_print
from rich.markup import escape

from comicbox.cli.parser import build_parser
from comicbox.exceptions import (
    ConfigurationError,
    OnlineLookupAbortedError,
    UnsupportedArchiveTypeError,
    UsageError,
)
from comicbox.run import Runner

# Each is a complete message for the user; a traceback adds nothing.
# ConfigError is confuse's: an unreadable -c file, or a value of the wrong
# type in a config file or env var.
_HANDLED_EXCEPTIONS = (
    UnsupportedArchiveTypeError,
    OnlineLookupAbortedError,
    ConfigurationError,
    ConfigError,
)

# `comicbox readinglist ...` and its short form `comicbox rl ...`.
_READING_LIST_COMMANDS = frozenset({"readinglist", "rl"})


def get_args(params: Sequence[str] | None = None) -> Namespace:
    """
    Parse CLI arguments into the config namespace.

    Config-tree args carry dotted dests naming their template path;
    ``set_args(dots=True)`` nests them. ``params`` is an argv-style
    sequence: ``params[0]`` is treated as the program name and dropped
    before parsing, mirroring ``sys.argv``. Pass ``None`` to parse
    ``sys.argv`` itself.
    """
    parser = build_parser()
    if params is not None:
        params = params[1:]
    cns = parser.parse_args(params)
    # --id is single-comic only; mass-tagging would mistag.
    explicit_ids = getattr(cns, "explicit_ids", None) or ()
    if explicit_ids and len(cns.paths or ()) > 1:
        parser.error("--id requires exactly one input path")
    return cns


def main(params: Sequence[str] | None = None) -> None:
    """Get CLI arguments and perform the operation on the archive."""
    argv = sys.argv if params is None else params
    if len(argv) > 1 and argv[1] == "doctor":
        # Before the Runner: building it resolves the config, which raises
        # on a bad one, and the doctor has to survive that to report it.
        # Imported here so a normal run never loads the doctor.
        from comicbox import doctor

        sys.exit(doctor.main(argv[2:]))
    if len(argv) > 1 and argv[1] in _READING_LIST_COMMANDS:
        # Its own parser and actions. Imported here so a normal run never
        # loads the reading-list package.
        from comicbox.readinglists import cli as readinglist_cli

        sys.exit(readinglist_cli.main(argv[2:]))
    cns = get_args(params)
    args = Namespace(comicbox=cns)

    try:
        # Building the runner resolves the config, so it's guarded too.
        runner = Runner(args)
        runner.run()
    except UsageError as exc:
        # The parser's own error style and exit status: the arguments are
        # wrong, which only the run could tell.
        build_parser().error(str(exc))
    except _HANDLED_EXCEPTIONS as exc:
        # Escaped: comic paths carry brackets ("[digital]") that rich
        # would otherwise swallow as markup, or reject outright.
        rich_print(f"[yellow]{escape(str(exc))}[/yellow]")
        sys.exit(1)
    if runner.failure_count:
        # Batch dispatch logs each failure and keeps going, so without
        # this a run where every file failed still exited 0. Serial runs
        # used to report it by letting the first failure escape, which
        # also abandoned every file behind it.
        rich_print(f"[yellow]{runner.failure_count} file(s) failed.[/yellow]")
        sys.exit(1)
