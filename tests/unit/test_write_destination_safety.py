"""
Write-destination collisions, refused before any archive is repacked.

Every one of these used to be found *after* the work: a batch repacked an
archive and then discovered its destination was taken, and two archives
converging on one name were decided by whichever thread claimed it first.
"""

from __future__ import annotations

import shutil
import threading
from typing import TYPE_CHECKING

import pytest

from comicbox.box import Comicbox
from comicbox.events import BatchFinished, Event, FileError
from comicbox.predict import predict_write_destination
from comicbox.write import (
    BulkWriteItem,
    DestinationOccupiedError,
    bulk_write,
    write_metadata,
)
from tests.const import (
    CB7_SOURCE_PATH,
    CBI_CBR_SOURCE_PATH,
    CIX_CBT_SOURCE_PATH,
    CIX_CBZ_SOURCE_PATH,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def tmp_cbz(tmp_path: Path) -> Path:
    """Fresh copy of the test CBZ for each test."""
    target = tmp_path / "test.cbz"
    shutil.copy(CIX_CBZ_SOURCE_PATH, target)
    return target


@pytest.fixture
def tmp_cbr(tmp_path: Path) -> Path:
    """Fresh copy of the test CBR for each test."""
    target = tmp_path / "test.cbr"
    shutil.copy(CBI_CBR_SOURCE_PATH, target)
    return target


def _spy_to_dict(monkeypatch: pytest.MonkeyPatch) -> list:
    """Record every metadata serialization the box performs."""
    calls: list = []
    original = Comicbox._to_dict

    def _spy(self, *args, **kwargs):
        calls.append(args)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Comicbox, "_to_dict", _spy)
    return calls


def test_writing_a_cbr_twice_refuses_the_second(tmp_cbr: Path) -> None:
    """
    The kept original's CBZ twin is what the second write collides with.

    ``delete_orig`` defaults off, so the first write leaves the CBR
    beside its new CBZ. Running the same batch again used to repack the
    whole archive before noticing.
    """
    cbz = tmp_cbr.with_suffix(".cbz")
    assert write_metadata(
        tmp_cbr, patch={"title": "one"}, formats=["comic_info"]
    ).written
    first_bytes = cbz.read_bytes()
    cbr_bytes = tmp_cbr.read_bytes()

    result = write_metadata(tmp_cbr, patch={"title": "two"}, formats=["comic_info"])

    assert not result.written
    assert isinstance(result.error, DestinationOccupiedError)
    assert result.error.kind == "convert"
    assert result.error.destination == cbz
    assert result.error.source == tmp_cbr
    # Neither file was touched.
    assert cbz.read_bytes() == first_bytes
    assert tmp_cbr.read_bytes() == cbr_bytes


def test_an_occupied_destination_is_refused_before_any_parse(
    tmp_cbr: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    ``dump()`` checks the destination before it loads a single source.

    The check used to sit inside ``_create_zipfile``, after the whole
    merge pipeline had run. This is the CLI path as well as the API one.
    """
    tmp_cbr.with_suffix(".cbz").write_bytes(b"already-here")
    calls = _spy_to_dict(monkeypatch)

    result = write_metadata(tmp_cbr, patch={"title": "x"}, formats=["comic_info"])

    assert isinstance(result.error, DestinationOccupiedError)
    assert result.error.kind == "convert"
    assert not calls


def test_bulk_write_preflight_refuses_before_any_write(
    tmp_cbr: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A batch's occupied destination costs no metadata parse at all."""
    tmp_cbr.with_suffix(".cbz").write_bytes(b"already-here")
    calls = _spy_to_dict(monkeypatch)
    items = [
        BulkWriteItem(
            path=tmp_cbr, patch={"title": "x"}, formats=frozenset({"COMIC_INFO"})
        )
    ]

    results = list(bulk_write(items))

    assert len(results) == 1
    assert isinstance(results[0].error, DestinationOccupiedError)
    assert not calls


def test_bulk_write_in_batch_collision_is_deterministic(tmp_path: Path) -> None:
    """
    Submission order decides the loser, every single time.

    Two same-stem archives converge on one .cbz. Before the preflight the
    winner was whichever thread claimed the destination first, so the
    same batch could report either file as the failure.
    """
    for run in range(10):
        run_dir = tmp_path / f"run{run}"
        run_dir.mkdir()
        cbt = run_dir / "Clash #001.cbt"
        cb7 = run_dir / "Clash #001.cb7"
        shutil.copy(CIX_CBT_SOURCE_PATH, cbt)
        shutil.copy(CB7_SOURCE_PATH, cb7)
        items = [
            BulkWriteItem(
                path=cbt, patch={"title": "a"}, formats=frozenset({"COMIC_INFO"})
            ),
            BulkWriteItem(
                path=cb7, patch={"title": "b"}, formats=frozenset({"COMIC_INFO"})
            ),
        ]

        results = {r.path: r for r in bulk_write(items, workers=2)}

        assert results[cbt].written is True
        refused = results[cb7]
        assert refused.written is False
        assert isinstance(refused.error, DestinationOccupiedError)
        assert refused.error.kind == "convert"
        assert refused.error.occupant == cbt
        assert refused.error.destination == run_dir / "Clash #001.cbz"


def test_bulk_write_refuses_one_path_named_twice(tmp_cbz: Path) -> None:
    """
    The same archive submitted twice loses its second submission.

    Two in-place repacks of one CBZ at once destroyed every page in
    roughly one run out of three; the claim caught it by race, this
    catches it by order.
    """
    items = [
        BulkWriteItem(
            path=tmp_cbz, patch={"title": f"t{i}"}, formats=frozenset({"COMIC_INFO"})
        )
        for i in range(2)
    ]

    results = list(bulk_write(items, workers=2))

    assert sum(r.written for r in results) == 1
    refused = next(r for r in results if not r.written)
    assert isinstance(refused.error, DestinationOccupiedError)
    assert refused.error.kind == "inflight"
    assert refused.error.occupant == tmp_cbz
    assert "already being written" in str(refused.error)


def test_bulk_write_preflight_false_restores_the_old_path(tmp_cbr: Path) -> None:
    """The escape hatch does the work first and refuses at the end."""
    tmp_cbr.with_suffix(".cbz").write_bytes(b"already-here")
    items = [
        BulkWriteItem(
            path=tmp_cbr, patch={"title": "x"}, formats=frozenset({"COMIC_INFO"})
        )
    ]

    results = list(bulk_write(items, preflight=False))

    assert len(results) == 1
    # Still refused -- by the on-disk check inside the write, as before.
    assert not results[0].written
    assert "already exists" in str(results[0].error)


def test_bulk_write_preflight_failures_report_their_own_index(
    tmp_path: Path, tmp_cbz: Path
) -> None:
    """A preflight failure emits FileError with its submitted position."""
    bad = tmp_path / "bad.cbz"
    bad.write_bytes(b"not a zip")
    items = [
        BulkWriteItem(
            path=tmp_cbz, patch={"title": "a"}, formats=frozenset({"COMIC_INFO"})
        ),
        BulkWriteItem(
            path=bad, patch={"title": "b"}, formats=frozenset({"COMIC_INFO"})
        ),
    ]
    events: list[Event] = []

    list(bulk_write(items, on_event=events.append))

    errors = [e for e in events if isinstance(e, FileError)]
    assert len(errors) == 1
    assert errors[0].path == bad
    assert errors[0].index == 1
    assert errors[0].total == 2


def test_bulk_write_preflight_failures_are_counted_in_the_summary(
    tmp_path: Path, tmp_cbz: Path
) -> None:
    """``BatchFinished`` counts a preflight refusal as an error, not a skip."""
    bad = tmp_path / "bad.cbz"
    bad.write_bytes(b"not a zip")
    items = [
        BulkWriteItem(
            path=tmp_cbz, patch={"title": "a"}, formats=frozenset({"COMIC_INFO"})
        ),
        BulkWriteItem(
            path=bad, patch={"title": "b"}, formats=frozenset({"COMIC_INFO"})
        ),
    ]
    events: list[Event] = []

    list(bulk_write(items, on_event=events.append))

    finished = events[-1]
    assert isinstance(finished, BatchFinished)
    assert finished.errored == 1
    assert finished.parsed == 1
    assert finished.total == 2


def test_bulk_write_preflight_failure_stops_the_batch(
    tmp_path: Path, tmp_cbz: Path
) -> None:
    """``stop_on_error`` cancels the survivors a preflight failure precedes."""
    bad = tmp_path / "bad.cbz"
    bad.write_bytes(b"not a zip")
    before = tmp_cbz.read_bytes()
    items = [
        BulkWriteItem(
            path=bad, patch={"title": "a"}, formats=frozenset({"COMIC_INFO"})
        ),
        BulkWriteItem(
            path=tmp_cbz, patch={"title": "b"}, formats=frozenset({"COMIC_INFO"})
        ),
    ]

    results = {r.path: r for r in bulk_write(items, stop_on_error=True)}

    assert results[bad].error is not None
    assert results[tmp_cbz].cancelled is True
    assert tmp_cbz.read_bytes() == before


def test_bulk_write_does_no_sniffing_at_call_time(
    tmp_cbz: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The pre-pass is lazy.

    A 20k-file batch off a network mount must not block the
    ``bulk_write()`` call, where ``cancel`` is never consulted.
    """
    calls: list = []

    def _counting(path, **kwargs):
        calls.append(path)
        return predict_write_destination(path, **kwargs)

    monkeypatch.setattr("comicbox.write.predict_write_destination", _counting)
    items = [
        BulkWriteItem(
            path=tmp_cbz, patch={"title": "a"}, formats=frozenset({"COMIC_INFO"})
        )
    ]

    iterator = bulk_write(items)
    assert not calls

    list(iterator)
    assert calls


def test_bulk_write_cancelled_before_the_first_next_never_sniffs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    A cancelled batch reports cancellations, not sniff errors.

    The corrupt file would fail the sniff; with cancel already set,
    nothing is sniffed at all.
    """
    bad = tmp_path / "bad.cbz"
    bad.write_bytes(b"not a zip")
    calls: list = []
    monkeypatch.setattr(
        "comicbox.write.predict_write_destination",
        lambda *a, **kw: calls.append(a),
    )
    items = [
        BulkWriteItem(path=bad, patch={"title": "a"}, formats=frozenset({"COMIC_INFO"}))
    ]
    cancel = threading.Event()
    cancel.set()

    results = list(bulk_write(items, cancel=cancel))

    assert len(results) == 1
    assert results[0].cancelled is True
    assert results[0].error is None
    assert not calls


def test_bulk_write_cancelled_mid_sniff_flushes_the_remainder(
    tmp_path: Path, tmp_cbz: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The pre-pass checks ``cancel`` between sniffs.

    Cancelling during the first item's sniff must report the corrupt
    second item as cancelled, not sniff it and report its error.
    """
    bad = tmp_path / "bad.cbz"
    bad.write_bytes(b"not a zip")
    cancel = threading.Event()
    sniffed: list = []

    def _cancelling(path, **kwargs):
        sniffed.append(path)
        cancel.set()
        return predict_write_destination(path, **kwargs)

    monkeypatch.setattr("comicbox.write.predict_write_destination", _cancelling)
    items = [
        BulkWriteItem(
            path=tmp_cbz, patch={"title": "a"}, formats=frozenset({"COMIC_INFO"})
        ),
        BulkWriteItem(
            path=bad, patch={"title": "b"}, formats=frozenset({"COMIC_INFO"})
        ),
    ]

    results = {r.path: r for r in bulk_write(items, cancel=cancel)}

    assert sniffed == [tmp_cbz]
    # The sniffed survivor is flushed as cancelled too: cancel means no
    # new writes start, and its sniff passing does not change that.
    assert results[tmp_cbz].cancelled is True
    assert results[bad].cancelled is True
    assert results[bad].error is None
