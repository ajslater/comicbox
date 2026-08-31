"""
Unit tests for filename prediction and conversion write safety.

The scheme filename ends in ``ext``, a metadata field rather than the
file's suffix, so a name can claim a format the archive isn't. Conversions
add a second hazard: archives differing only by suffix all convert to one
``.cbz``.
"""

from __future__ import annotations

import shutil
import zipfile
from typing import TYPE_CHECKING

import pytest

from comicbox.box import Comicbox
from comicbox.box.archive.write import (
    _RECOMPRESS_SUFFIX,
    _claim_destination,
    _release_destination,
)
from comicbox.config import get_config
from comicbox.exceptions import ArchiveWriteError
from comicbox.write import BulkWriteItem, bulk_write
from tests.const import CIX_CBT_SOURCE_PATH, CIX_CBZ_SOURCE_PATH

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
    _claim_destination(dest)
    try:
        with pytest.raises(ArchiveWriteError):
            _claim_destination(dest)
    finally:
        _release_destination(dest)
    # Free again once that write is done.
    _claim_destination(dest)
    _release_destination(dest)


def test_conversion_temp_files_do_not_collide(tmp_path: Path) -> None:
    """Same-stem sources must not share one temp path."""
    cbt = tmp_path / "Temp v1 #001 (2001).cbt"
    cb7 = tmp_path / "Temp v1 #001 (2001).cb7"

    assert cbt.with_name(cbt.name + _RECOMPRESS_SUFFIX) != cb7.with_name(
        cb7.name + _RECOMPRESS_SUFFIX
    )


def test_same_stem_conversions_keep_both_originals(tmp_path: Path) -> None:
    """
    Two archives converging on one .cbz must not destroy each other.

    Both convert to the same destination name. Whichever loses has to
    fail cleanly — before, its original was unlinked while its contents
    only ever reached a file the winner overwrote.
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
    assert len(written) == 1
    assert len(failed) == 1
    # Refused either as an in-flight claim or as a finished file, depending
    # on whether the two writes actually overlapped.
    error = str(failed[0].error)
    assert "already being written" in error or "already exists" in error
    # Neither archive is destroyed: the loser never reached the destination.
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

    _claim_destination(dest)
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

    with pytest.raises(ArchiveWriteError, match="already exists"), Comicbox(cbz) as car:
        car.rename_file()

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

    _claim_destination(dest)
    try:
        with (
            pytest.raises(ArchiveWriteError, match="already being written"),
            Comicbox(cbz) as car,
        ):
            car.rename_file()
    finally:
        _release_destination(dest)

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
