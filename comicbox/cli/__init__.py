"""Cli for comicbox."""

import sys
from argparse import Namespace
from collections.abc import Sequence
from types import MappingProxyType
from typing import Any

from rich import print as rich_print

from comicbox.box.online_lookup import OnlineLookupAbortedError
from comicbox.cli.parser import _build_parser
from comicbox.exceptions import UnsupportedArchiveTypeError
from comicbox.run import Runner

_HANDLED_EXCEPTIONS = (UnsupportedArchiveTypeError, OnlineLookupAbortedError)
_QUIET_LOGLEVEL = MappingProxyType({1: "INFO", 2: "SUCCESS", 3: "WARNING", 4: "ERROR"})


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
    """
    Parse CLI arguments and reshape into the nested config namespace.

    ``params`` is an argv-style sequence: ``params[0]`` is treated as the
    program name and dropped before parsing, mirroring ``sys.argv``. Pass
    ``None`` to parse ``sys.argv`` itself.
    """
    parser = _build_parser()
    if params is not None:
        params = params[1:]
    cns = parser.parse_args(params)
    # --id is single-comic only; mass-tagging would mistag.
    explicit_ids = getattr(cns, "explicit_ids", None) or ()
    if explicit_ids and len(cns.paths or ()) > 1:
        parser.error("--id requires exactly one input path")
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
