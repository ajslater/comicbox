"""
Lazy rarfile import with comicbox's sub-second timestamp patch.

rarfile <= 4.5 raises ``ValueError: microsecond must be in 0..999999`` from
``RarFile.__init__`` when a RAR3 extended timestamp carries a sub-second
remainder of one second or more, which some third-party packers write. Its
``_parse_xtime`` builds the remainder from three bytes (up to 1.68 seconds
in 100ns units) and hands it to ``to_nsdatetime`` unclamped. Nothing in the
parse chain catches the error, so the archive cannot be opened at all.

``import_rarfile()`` is the sanctioned way to import rarfile for archive
construction. It wraps ``to_nsdatetime`` to carry whole seconds out of the
nanosecond argument.

``rar_unsupported_reason()`` says whether this host can extract RAR members
at all, by actually extracting one.

Never import rarfile at module scope here. Reading a CBZ must not load
rarfile at all (tests/unit/test_archive_read.py::
test_cbz_read_does_not_load_py7zr_or_rarfile).
"""

from __future__ import annotations

import shutil
import threading
from datetime import UTC, datetime, timedelta
from functools import cache, wraps
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import ModuleType

__all__ = ("import_rarfile", "rar_unsupported_reason")

# A 110 byte RAR5 archive holding one compressed member, made with
# ``rar a -ma5 -m5 -ep _rar_probe.rar probe.txt`` from 64 copies of the
# line "comicbox rar probe". It must stay compressed: rarfile reads stored
# members itself, so a stored probe would pass with no tool installed.
_TOOL_PROBE_PATH = Path(__file__).with_name("_rar_probe.rar")
_TOOL_PROBE_MEMBER = "probe.txt"

_NS_PER_SECOND = 1_000_000_000
_PROBE_DATETIME = datetime(2020, 1, 1, tzinfo=UTC)
# Any remainder of a second or more trips the bug. The value is arbitrary.
_PROBE_NSEC = 1_500_000_000
# Guards against stacking wrappers when threads detect archives concurrently.
_PATCH_LOCK = threading.Lock()


def _is_nsec_overflow_broken(rarfile: ModuleType) -> bool:
    """Report whether this rarfile still crashes on an overlong remainder."""
    try:
        rarfile.to_nsdatetime(_PROBE_DATETIME, _PROBE_NSEC)
    except ValueError:
        return True
    return False


def _patch_nsec_overflow(rarfile: ModuleType) -> None:
    """Carry whole seconds out of to_nsdatetime's nanosecond argument."""
    with _PATCH_LOCK:
        # Probing behavior instead of marking the module makes this a no-op
        # both when already patched and when a future rarfile fixes the bug.
        if not _is_nsec_overflow_broken(rarfile):
            return
        original = rarfile.to_nsdatetime

        @wraps(original)
        def to_nsdatetime(dttm: datetime, nsec: int) -> datetime:
            if nsec >= _NS_PER_SECOND:
                extra_seconds, nsec = divmod(nsec, _NS_PER_SECOND)
                dttm = dttm + timedelta(seconds=extra_seconds)
            return original(dttm, nsec)

        # Patching a module attribute is valid at runtime, but ModuleType
        # declares no such attribute for the type checkers to check against.
        rarfile.to_nsdatetime = to_nsdatetime  # pyright: ignore[reportAttributeAccessIssue], # ty: ignore[unresolved-attribute]


@cache
def import_rarfile() -> ModuleType:
    """Import rarfile, patched for the sub-second timestamp overflow."""
    import rarfile

    _patch_nsec_overflow(rarfile)
    return rarfile


@cache
def rar_unsupported_reason() -> str:
    """
    Return why this host can't extract RAR members, or "" if it can.

    rarfile shells out to the first tool whose version check passes --
    unrar, unar, 7z, 7zz, then bsdtar -- but passing that check proves
    little. rarfile 4.5's bsdtar command line opens a file named ``--``,
    and 7-Zip builds without the RAR codec (Homebrew's 7zz) answer
    "Unsupported Method", so both fail every compressed member while
    looking installed. Extracting a real compressed member with whatever
    tool rarfile picked is the only test that answers the question.

    Cached: the host's tools don't change under a running process.
    """
    rarfile = import_rarfile()
    try:
        with rarfile.RarFile(_TOOL_PROBE_PATH) as archive:
            archive.read(_TOOL_PROBE_MEMBER)
    except (rarfile.Error, OSError) as exc:
        unrar: str = rarfile.UNRAR_TOOL
        if not shutil.which(unrar):
            return f"'{unrar}' not on path"
        return f"'{unrar}' cannot extract RAR archives: {exc}"
    return ""
