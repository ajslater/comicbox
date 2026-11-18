"""
Give a copy of a comic what the comic had beside its bytes.

A write that replaces a comic with a patched copy keeps the comic's mode,
its owner and group where this process may set them, and its extended
attributes where the standard library can read them: on Linux, not on macOS
or Windows.
"""

from __future__ import annotations

import os
import stat
from contextlib import suppress
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from pathlib import Path


def _keep_owner(source_stat: os.stat_result, copy: Path) -> None:
    """Give the copy the comic's owner and group, or its group alone."""
    if not hasattr(os, "chown"):  # pragma: no cover
        return
    try:
        os.chown(copy, source_stat.st_uid, source_stat.st_gid)
    except PermissionError:
        # Only root may give a file away, but a member may set its group.
        with suppress(PermissionError):
            os.chown(copy, -1, source_stat.st_gid)


def _keep_xattrs(source: Path, copy: Path) -> None:
    """Copy the comic's extended attributes, where ``os`` has them."""
    if not hasattr(os, "listxattr"):
        return
    try:
        names = os.listxattr(source)
    except OSError as exc:
        logger.debug(f"{source}: extended attributes not kept: {exc}")
        return
    for name in names:
        with suppress(OSError):
            os.setxattr(copy, name, os.getxattr(source, name))


def keep_attributes(source: Path, copy: Path) -> None:
    """Give a copy the comic's extended attributes, owner, group and mode."""
    source_stat = source.stat()
    _keep_xattrs(source, copy)
    _keep_owner(source_stat, copy)
    # After the owner: a change of owner can clear the set-id bits.
    copy.chmod(stat.S_IMODE(source_stat.st_mode))
