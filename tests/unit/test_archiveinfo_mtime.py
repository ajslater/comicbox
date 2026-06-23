"""Unit tests for ArchiveInfo.mtime datetime normalization."""

from __future__ import annotations

import pickle
from datetime import datetime, timezone

from rarfile import nsdatetime

from comicbox.box.archive.archiveinfo import ArchiveInfo


class _FakeRarInfo:
    """Quacks like rarfile.RarInfo for ArchiveInfo dispatch."""

    def __init__(self, mtime: datetime | None) -> None:
        self.mtime = mtime


def test_rar_nsdatetime_is_coerced_to_picklable_datetime() -> None:
    """
    Rarfile's nsdatetime breaks ProcessPoolExecutor result transfer.

    It is a datetime subclass with no __reduce__, so unpickling it in the
    parent raises TypeError and poisons the worker pool. ArchiveInfo.mtime
    must hand back a plain, picklable datetime.
    """
    ns = nsdatetime(2007, 5, 1, 12, 30, 15, nanosecond=123456789, tzinfo=timezone.utc)
    assert type(ns) is nsdatetime  # real subclass instance

    out = ArchiveInfo.mtime(_FakeRarInfo(ns))

    assert type(out) is datetime
    assert out == datetime(2007, 5, 1, 12, 30, 15, 123456, tzinfo=timezone.utc)
    # Must survive the pickle round-trip that crosses the pool boundary.
    assert pickle.loads(pickle.dumps(out)) == out  # noqa: S301


def test_naive_rar_nsdatetime_gets_utc_and_is_picklable() -> None:
    """A naive nsdatetime is made tz-aware and still coerced to datetime."""
    ns = nsdatetime(2007, 5, 1, 12, 30, 15, nanosecond=500_000_000)

    out = ArchiveInfo.mtime(_FakeRarInfo(ns))

    assert type(out) is datetime
    assert out.tzinfo == timezone.utc
    assert pickle.loads(pickle.dumps(out)) == out  # noqa: S301


def test_none_rar_mtime_passes_through() -> None:
    """A missing mtime stays None."""
    assert ArchiveInfo.mtime(_FakeRarInfo(None)) is None
