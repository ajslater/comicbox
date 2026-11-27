"""
Unit tests for filename prediction and conversion write safety.

The scheme filename ends in ``ext``, a metadata field rather than the
file's suffix, so a name can claim a format the archive isn't. Conversions
add a second hazard: archives differing only by suffix all convert to one
``.cbz``.
"""

from __future__ import annotations

import shutil
import threading
import zipfile
from contextlib import suppress
from typing import TYPE_CHECKING, Any

import pytest

from comicbox.box import Comicbox
from comicbox.box.archive.write import (
    ComicboxArchiveWrite,
    _claim_destination,
    _release_destination,
    tmp_archive_path,
)
from comicbox.config import get_config
from comicbox.exceptions import DestinationOccupiedError
from comicbox.write import BulkWriteItem, bulk_write
from tests.const import CB7_SOURCE_PATH, CIX_CBT_SOURCE_PATH, CIX_CBZ_SOURCE_PATH

if TYPE_CHECKING:
    from pathlib import Path

_YAML = frozenset({"COMICBOX_YAML"})


def test_predict_filename_keeps_a_non_cbz_suffix(tmp_path: Path) -> None:
    """A CBT is never predicted as a name claiming to be a zip."""
    cbt = tmp_path / "Predict v1999 #001 (1999).cbt"
    shutil.copy(CIX_CBT_SOURCE_PATH, cbt)

    with Comicbox(cbt) as car:
        predicted = car.predict_filename()

    assert predicted.endswith(".cbt")


def test_predict_filename_survives_a_deleted_ext_key(tmp_path: Path) -> None:
    """
    A config that skips ``ext`` still predicts the real suffix.

    ``ext`` is only ever parsed from the filename, so a caller that trims
    the fields it doesn't consume drops it — and comicfn2dict then falls
    back to its "cbz" default, naming every other format a zip.
    """
    cbt = tmp_path / "Deleted v1999 #004 (1999).cbt"
    shutil.copy(CIX_CBT_SOURCE_PATH, cbt)
    config = get_config({"comicbox": {"general": {"delete_keys": ("ext",)}}})

    with Comicbox(cbt, config=config) as car:
        predicted = car.predict_filename()

    assert predicted.endswith(".cbt")


def test_predict_filename_ignores_a_stale_embedded_ext(tmp_path: Path) -> None:
    """An ``ext`` some tagger wrote into the archive cannot rename it."""
    cbz = tmp_path / "Stale v1999 #005 (1999).cbz"
    shutil.copy(CIX_CBZ_SOURCE_PATH, cbz)
    with zipfile.ZipFile(cbz, "a") as zf:
        zf.writestr("comicbox.yaml", "comicbox:\n  ext: cbr\n  series:\n    name: S\n")

    with Comicbox(cbz) as car:
        predicted = car.predict_filename()

    assert predicted.endswith(".cbz")


def test_predict_filename_keeps_a_cbz_suffix(tmp_path: Path) -> None:
    """The common case is unchanged."""
    cbz = tmp_path / "Predict v1999 #002 (1999).cbz"
    shutil.copy(CIX_CBZ_SOURCE_PATH, cbz)

    with Comicbox(cbz) as car:
        predicted = car.predict_filename()

    assert predicted.endswith(".cbz")


def test_rename_file_lands_on_the_predicted_name(tmp_path: Path) -> None:
    """The rename and the prediction can't disagree."""
    cbt = tmp_path / "Rename v1999 #003 (1999).cbt"
    shutil.copy(CIX_CBT_SOURCE_PATH, cbt)

    with Comicbox(cbt) as car:
        predicted = car.predict_filename()
        car.rename_file()
        landed = car.get_path()

    assert landed is not None
    assert landed.name == predicted
    assert landed.suffix == ".cbt"
    assert landed.exists()


def test_a_claimed_destination_is_refused(tmp_path: Path) -> None:
    """
    Two writers cannot hold one conversion destination.

    The completed-file check can't see a conversion still in flight, so
    without the claim two same-stem archives both pass it, and the second
    replaces the first's finished file while ``delete_orig`` unlinks both
    originals.
    """
    dest = tmp_path / "Held v1 #001 (2001).cbz"
    # The source path only labels the refusal; any path stands in for the
    # rival writer that would be holding this destination.
    source = tmp_path / "Held v1 #001 (2001).cbt"
    _claim_destination(dest, source)
    try:
        with pytest.raises(DestinationOccupiedError) as exc_info:
            _claim_destination(dest, source)
    finally:
        _release_destination(dest)
    assert exc_info.value.kind == "inflight"
    assert exc_info.value.destination == dest
    # Free again once that write is done.
    _claim_destination(dest, source)
    _release_destination(dest)


def test_a_claim_holds_the_file_under_any_name(tmp_path: Path) -> None:
    """A link to a file being written is refused, as its own name is."""
    target = tmp_path / "cw1.cbz"
    target.write_bytes(b"")
    link = tmp_path / "lib" / "link0.cbz"
    link.parent.mkdir()
    link.symlink_to(target)
    _claim_destination(target, target)
    try:
        with pytest.raises(DestinationOccupiedError) as exc_info:
            _claim_destination(link, link)
    finally:
        _release_destination(target)
    assert exc_info.value.destination == link
    _claim_destination(link, link)
    _release_destination(link)


def test_a_claim_is_released_once_its_file_exists(tmp_path: Path) -> None:
    """
    A conversion claims a name with nothing there and releases a new file.

    The release goes by the claiming path, since the file's key has changed
    since the claim; released any other way, the name stays held for good.
    """
    dest = tmp_path / "Foo.cbz"
    _claim_destination(dest, tmp_path / "Foo.cbr")
    dest.write_bytes(b"")
    _release_destination(dest)
    _claim_destination(dest, tmp_path / "Foo.cbt")
    _release_destination(dest)


def test_conversion_temp_files_do_not_collide(tmp_path: Path) -> None:
    """Same-stem sources must not share one temp path."""
    cbt = tmp_path / "Temp v1 #001 (2001).cbt"
    cb7 = tmp_path / "Temp v1 #001 (2001).cb7"

    assert tmp_archive_path(cbt) != tmp_archive_path(cb7)


def _convert_same_stem_pair(tmp_path: Path) -> tuple[Path, Path, list, list]:
    """
    Convert two archives that converge on one .cbz name.

    Both convert to the same destination, so one of them has to lose.
    """
    cbt = tmp_path / "Clash v1 #001 (2001).cbt"
    cb7 = tmp_path / "Clash v1 #001 (2001).cb7"
    shutil.copy(CIX_CBT_SOURCE_PATH, cbt)
    shutil.copy(CIX_CBT_SOURCE_PATH, cb7)

    results = list(
        bulk_write(
            [
                BulkWriteItem(path=cbt, patch={"title": "a"}, formats=_YAML),
                BulkWriteItem(path=cb7, patch={"title": "b"}, formats=_YAML),
            ]
        )
    )

    written = [r for r in results if r.written]
    failed = [r for r in results if not r.written]
    return cbt, cb7, written, failed


def test_same_stem_conversions_refuse_the_loser(tmp_path: Path) -> None:
    """Exactly one of the two claims the destination; the other is refused."""
    cbt, _cb7, written, failed = _convert_same_stem_pair(tmp_path)

    assert len(written) == 1
    assert len(failed) == 1
    # The batch preflight decides this by submission order, so the CBT
    # submitted first is always the one named as the occupant.
    error = failed[0].error
    assert isinstance(error, DestinationOccupiedError)
    assert error.kind == "convert"
    assert error.occupant == cbt


def test_same_stem_conversions_keep_both_originals(tmp_path: Path) -> None:
    """
    Two archives converging on one .cbz must not destroy each other.

    The loser has to fail cleanly — before, its original was unlinked while
    its contents only ever reached a file the winner overwrote.
    """
    cbt, cb7, _written, _failed = _convert_same_stem_pair(tmp_path)

    assert cbt.exists()
    assert cb7.exists()
    assert (tmp_path / "Clash v1 #001 (2001).cbz").exists()


def test_conversion_does_not_embed_a_stale_ext(tmp_path: Path) -> None:
    """The metadata written into a converted archive can't claim the old format."""
    cbt = tmp_path / "Embed v1 #001 (2001).cbt"
    shutil.copy(CIX_CBT_SOURCE_PATH, cbt)

    result = next(
        iter(bulk_write([BulkWriteItem(path=cbt, patch={"title": "y"}, formats=_YAML)]))
    )

    assert result.written
    cbz = result.final_path
    assert cbz is not None
    assert cbz.suffix == ".cbz"
    with zipfile.ZipFile(cbz) as zf:
        names = [n for n in zf.namelist() if n.endswith("comicbox.yaml")]
        assert names
        embedded = zf.read(names[0]).decode()
    assert "ext:" not in embedded


def test_a_conversion_respects_a_held_destination(tmp_path: Path) -> None:
    """
    The write path consults the claim, not just the finished-file check.

    Holding the destination stands in for a conversion still in flight,
    which leaves nothing on disk for ``_get_new_archive_path`` to see.
    """
    cbt = tmp_path / "Wired v1 #001 (2001).cbt"
    shutil.copy(CIX_CBT_SOURCE_PATH, cbt)
    dest = tmp_path / "Wired v1 #001 (2001).cbz"

    _claim_destination(dest, cbt)
    try:
        result = next(
            iter(
                bulk_write(
                    [BulkWriteItem(path=cbt, patch={"title": "z"}, formats=_YAML)]
                )
            )
        )
    finally:
        _release_destination(dest)

    assert not result.written
    # The preflight can't see an in-memory claim -- nothing is on disk --
    # so the write path's own claim is what refuses this one.
    assert isinstance(result.error, DestinationOccupiedError)
    assert result.error.kind == "inflight"
    assert "already being written" in str(result.error)
    assert cbt.exists()
    assert not dest.exists()


def test_rename_refuses_an_existing_destination(tmp_path: Path) -> None:
    """
    A rename cannot silently eat the file already at the predicted name.

    Path.rename() replaces the destination on posix, so two archives whose
    metadata predicts one name — the same issue carried twice, or a scheme
    that renders too few distinguishing fields — left only the last one
    written, with no error and no log line saying anything was lost.
    """
    cbz = tmp_path / "Rename v1999 #006 (1999).cbz"
    shutil.copy(CIX_CBZ_SOURCE_PATH, cbz)
    with Comicbox(cbz) as car:
        occupied = tmp_path / car.predict_filename()
    occupied.write_bytes(b"already-here")

    with (
        pytest.raises(DestinationOccupiedError, match="already exists") as exc_info,
        Comicbox(cbz) as car,
    ):
        car.rename_file()
    assert exc_info.value.kind == "rename"
    assert exc_info.value.destination == occupied
    assert exc_info.value.source == cbz

    # Both files survive: the destination is untouched and the source stays
    # where it was, so a later run can still find it.
    assert occupied.read_bytes() == b"already-here"
    assert cbz.exists()


def test_rename_respects_a_held_destination(tmp_path: Path) -> None:
    """
    A rename consults the in-flight claim, like a conversion does.

    Holding the destination stands in for another thread's rename that
    hasn't landed yet, which leaves nothing on disk for the exists() check
    to see.
    """
    cbz = tmp_path / "Rename v1999 #007 (1999).cbz"
    shutil.copy(CIX_CBZ_SOURCE_PATH, cbz)
    with Comicbox(cbz) as car:
        dest = tmp_path / car.predict_filename()

    _claim_destination(dest, cbz)
    try:
        with (
            pytest.raises(
                DestinationOccupiedError, match="already being written"
            ) as ei,
            Comicbox(cbz) as car,
        ):
            car.rename_file()
    finally:
        _release_destination(dest)
    assert ei.value.kind == "inflight"

    assert cbz.exists()
    assert not dest.exists()


def test_rename_to_the_same_name_is_not_a_collision(tmp_path: Path) -> None:
    """An archive already at its predicted name must not refuse itself."""
    cbz = tmp_path / "Idempotent v1999 #008 (1999).cbz"
    shutil.copy(CIX_CBZ_SOURCE_PATH, cbz)
    with Comicbox(cbz) as car:
        car.rename_file()
        landed = car.get_path()
    assert landed is not None

    # Renaming the already-renamed archive is a no-op, not "already exists".
    with Comicbox(landed) as car:
        car.rename_file()
        again = car.get_path()

    assert again == landed
    assert landed.exists()


def test_a_rename_that_only_changes_case_is_carried_out(tmp_path: Path) -> None:
    """B3: on a case-insensitive disk it logged "Renamed" and renamed nothing."""
    cbz = tmp_path / "x.cbz"
    shutil.copy(CIX_CBZ_SOURCE_PATH, cbz)
    with Comicbox(cbz) as car:
        predicted = car.predict_filename()
    lowered = tmp_path / predicted.lower()
    cbz.rename(lowered)

    with Comicbox(lowered) as car:
        car.rename_file()

    assert [path.name for path in tmp_path.iterdir()] == [predicted]


def test_a_rename_onto_its_own_name_says_nothing(tmp_path: Path) -> None:
    from loguru import logger

    cbz = tmp_path / "x.cbz"
    shutil.copy(CIX_CBZ_SOURCE_PATH, cbz)
    with Comicbox(cbz) as car:
        car.rename_file()
        landed = car.get_path()
    assert landed is not None
    messages: list[str] = []
    handler = logger.add(messages.append, format="{message}")
    try:
        with Comicbox(landed) as car:
            car.rename_file()
    finally:
        logger.remove(handler)

    assert not [message for message in messages if "Renamed" in message]
    assert landed.exists()


def _rename_messages(path: Path) -> tuple[list[str], Path | None]:
    from loguru import logger

    messages: list[str] = []
    handler = logger.add(messages.append, format="{message}")
    try:
        with Comicbox(path) as car:
            car.rename_file()
            landed = car.get_path()
    finally:
        logger.remove(handler)
    return messages, landed


@pytest.mark.parametrize("link", ["hard", "symbolic"])
def test_a_rename_onto_another_name_for_itself_says_so(
    tmp_path: Path, link: str
) -> None:
    """A3: onto a hard link of itself, rename logged "Renamed" and did nothing."""
    cbz = tmp_path / "x.cbz"
    shutil.copy(CIX_CBZ_SOURCE_PATH, cbz)
    with Comicbox(cbz) as car:
        predicted = tmp_path / car.predict_filename()
    if link == "hard":
        predicted.hardlink_to(cbz)
    else:
        predicted.symlink_to(cbz.name)

    messages, landed = _rename_messages(cbz)

    assert not [message for message in messages if "Renamed" in message]
    assert [m.strip() for m in messages if m.startswith("Not renamed")] == [
        f"Not renamed: {predicted} is already a name for {cbz}"
    ]
    assert landed == cbz
    assert cbz.is_file()
    assert not cbz.is_symlink()
    assert predicted.exists()


def test_a_link_is_never_renamed_onto_its_target(tmp_path: Path) -> None:
    """Renaming a link onto the file it names would leave a link to itself."""
    real = tmp_path / "A.cbz"
    shutil.copy(CIX_CBZ_SOURCE_PATH, real)
    link = tmp_path / "a.cbz"
    try:
        link.symlink_to(real.name)
    except FileExistsError:
        pytest.skip("a case-insensitive disk cannot hold both names")

    assert not Comicbox._respell(link, real)

    assert real.is_file()
    assert not real.is_symlink()


def test_a_link_still_changes_the_case_of_its_own_name(tmp_path: Path) -> None:
    """On a case-insensitive disk a link's name is respelled like a file's."""
    real = tmp_path / "real" / "x.cbz"
    real.parent.mkdir()
    shutil.copy(CIX_CBZ_SOURCE_PATH, real)
    library = tmp_path / "library"
    library.mkdir()
    link = library / "x.cbz"
    link.symlink_to(real)
    respelled = library / "X.cbz"
    if not respelled.exists():
        pytest.skip("a case-sensitive disk holds the two names apart")

    assert Comicbox._respell(link, respelled)

    assert [path.name for path in library.iterdir()] == ["X.cbz"]
    assert respelled.is_symlink()
    assert real.is_file()


def test_a_claim_holds_every_case_spelling_of_a_new_name(tmp_path: Path) -> None:
    """A7: ``issue.cbz`` held refuses ``ISSUE.cbz``, one file on most disks."""
    dest = tmp_path / "issue.cbz"
    other = tmp_path / "ISSUE.cbz"
    _claim_destination(dest, tmp_path / "issue.cbt")
    try:
        with pytest.raises(DestinationOccupiedError) as exc_info:
            _claim_destination(other, tmp_path / "ISSUE.cb7")
    finally:
        _release_destination(dest)
    assert exc_info.value.kind == "inflight"
    _claim_destination(other, tmp_path / "ISSUE.cb7")
    _release_destination(other)


def _case_insensitive(directory: Path) -> bool:
    probe = directory / "case-probe"
    probe.write_bytes(b"")
    try:
        return (directory / "CASE-PROBE").exists()
    finally:
        probe.unlink()


@pytest.mark.parametrize("preflight", [True, False])
def test_concurrent_case_variant_conversions_keep_one_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, preflight: bool
) -> None:
    """
    A7: ``issue.cbt`` and ``ISSUE.cb7`` both convert to one CBZ there.

    Both writers passed the claim and the finished-file check, the second
    replaced the first's CBZ, and under ``delete_orig`` both originals
    were unlinked: one comic gone. The barrier holds each writer after its
    pages are copied so the two overlap; one that is refused never reaches
    it, and the other then waits out the short timeout.
    """
    if not _case_insensitive(tmp_path):
        pytest.skip("this disk is case-sensitive")
    cbt = tmp_path / "issue.cbt"
    cb7 = tmp_path / "ISSUE.cb7"
    shutil.copy(CIX_CBT_SOURCE_PATH, cbt)
    shutil.copy(CB7_SOURCE_PATH, cb7)
    barrier = threading.Barrier(2, timeout=1)
    original = ComicboxArchiveWrite._copy_archive_files_to_new_archive

    def copy_then_wait(self: ComicboxArchiveWrite, *args: Any, **kwargs: Any) -> None:
        original(self, *args, **kwargs)
        with suppress(threading.BrokenBarrierError):
            barrier.wait()

    monkeypatch.setattr(
        ComicboxArchiveWrite, "_copy_archive_files_to_new_archive", copy_then_wait
    )
    items = [
        BulkWriteItem(path=path, patch={"title": "x"}, formats=_YAML)
        for path in (cbt, cb7)
    ]
    config = get_config({"comicbox": {"general": {"delete_orig": True}}})

    results = list(
        bulk_write(items, workers=2, base_config=config, preflight=preflight)
    )

    written = [result for result in results if result.written]
    refused = [result for result in results if not result.written]
    assert len(written) == 1
    assert len(refused) == 1
    assert isinstance(refused[0].error, DestinationOccupiedError)
    assert refused[0].path.exists()
    assert not written[0].path.exists()
