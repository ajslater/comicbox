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

Never import rarfile at module scope here. Reading a CBZ must not load
rarfile at all (tests/unit/test_archive_read.py::
test_cbz_read_does_not_load_py7zr_or_rarfile).
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from functools import cache, wraps
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import ModuleType

__all__ = ("import_rarfile",)

_NS_PER_SECOND = 1_000_000_000
_PROBE_DATETIME = datetime(2020, 1, 1, tzinfo=timezone.utc)
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
        # declares no such attribute for basedpyright to check against.
        rarfile.to_nsdatetime = to_nsdatetime  # pyright: ignore[reportAttributeAccessIssue]


@cache
def import_rarfile() -> ModuleType:
    """Import rarfile, patched for the sub-second timestamp overflow."""
    import rarfile

    _patch_nsec_overflow(rarfile)
    return rarfile
