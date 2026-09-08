"""Cli for comicbox."""

import sys
from argparse import Namespace
from collections.abc import Sequence

from rich import print as rich_print

from comicbox.box.online_lookup import OnlineLookupAbortedError
from comicbox.cli.parser import build_parser
from comicbox.exceptions import UnsupportedArchiveTypeError
from comicbox.run import Runner

_HANDLED_EXCEPTIONS = (UnsupportedArchiveTypeError, OnlineLookupAbortedError)


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
    cns = get_args(params)
    args = Namespace(comicbox=cns)

    runner = Runner(args)
    try:
        runner.run()
    except _HANDLED_EXCEPTIONS as exc:
        rich_print(f"[yellow]{exc}[/yellow]")
        sys.exit(1)
    if runner.failure_count:
        # Batch dispatch logs each failure and keeps going, so without
        # this a run where every file failed still exited 0. Serial runs
        # used to report it by letting the first failure escape, which
        # also abandoned every file behind it.
        rich_print(f"[yellow]{runner.failure_count} file(s) failed.[/yellow]")
        sys.exit(1)
