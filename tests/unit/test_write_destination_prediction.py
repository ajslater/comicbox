"""
Where a write would land, predicted without opening the archive.

``write_metadata(dry_run=True)`` previews the payload and reports no
destination at all; this is the destination preview, and it has to be
cheap enough to run over a whole batch before any of it is written.
"""

from __future__ import annotations

import shutil
from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from comicbox.box import Comicbox
from comicbox.config import get_config
from comicbox.exceptions import UnsupportedArchiveTypeError
from comicbox.predict import predict_write_destination
from tests.const import (
    CB7_SOURCE_PATH,
    CBI_CBR_SOURCE_PATH,
    CIX_CBT_SOURCE_PATH,
    CIX_CBZ_SOURCE_PATH,
    PDF_SOURCE_PATH,
)

if TYPE_CHECKING:
    from pathlib import Path


def _copy(source: Path, tmp_path: Path, name: str) -> Path:
    target = tmp_path / name
    shutil.copy(source, target)
    return target


def test_a_cbz_is_written_in_place(tmp_path: Path) -> None:
    """A zip is rewritten where it sits; nothing converts."""
    cbz = _copy(CIX_CBZ_SOURCE_PATH, tmp_path, "Predict #001.cbz")

    dest = predict_write_destination(cbz)

    assert dest.path == cbz
    assert dest.destination == cbz
    assert dest.converts is False
    assert dest.occupied is False


@pytest.mark.parametrize(
    ("source", "name"),
    [
        (CBI_CBR_SOURCE_PATH, "Predict #002.cbr"),
        (CIX_CBT_SOURCE_PATH, "Predict #003.cbt"),
        (CB7_SOURCE_PATH, "Predict #004.cb7"),
    ],
)
def test_an_unwritable_archive_repacks_to_a_cbz(
    tmp_path: Path, source: Path, name: str
) -> None:
    """CBR/CBT/CB7 cannot be written, so a write repacks them."""
    archive = _copy(source, tmp_path, name)

    dest = predict_write_destination(archive)

    assert dest.destination == archive.with_suffix(".cbz")
    assert dest.converts is True
    assert dest.occupied is False


def test_a_pdf_is_written_in_place_by_default(tmp_path: Path) -> None:
    """PDF metadata is updated in the pdf itself unless a convert is asked for."""
    pdf = _copy(PDF_SOURCE_PATH, tmp_path, "Predict #005.pdf")

    dest = predict_write_destination(pdf)

    assert dest.destination == pdf
    assert dest.converts is False


def test_a_pdf_converts_when_the_config_asks(tmp_path: Path) -> None:
    """``convert.cbz`` is the only thing that moves a pdf write off the pdf."""
    pdf = _copy(PDF_SOURCE_PATH, tmp_path, "Predict #006.pdf")
    cfg = get_config()
    cfg = replace(cfg, convert=replace(cfg.convert, cbz=True))

    dest = predict_write_destination(pdf, base_config=cfg)

    assert dest.destination == pdf.with_suffix(".cbz")
    assert dest.converts is True


def test_predict_sniffs_content_not_suffix(tmp_path: Path) -> None:
    """
    The archive's bytes decide, never its name.

    A CBZ misnamed ``.cbr`` is still a zip, so it is rewritten in place
    and nothing converts. Deciding from the suffix would have reported a
    conversion to a file that is the archive itself.
    """
    mislabeled = _copy(CIX_CBZ_SOURCE_PATH, tmp_path, "Mislabeled #001.cbr")

    dest = predict_write_destination(mislabeled)

    assert dest.destination == mislabeled
    assert dest.converts is False
    assert dest.occupied is False


def test_a_taken_destination_is_reported_occupied(tmp_path: Path) -> None:
    """The CBZ twin of a kept original is what makes a later write fail."""
    cbr = _copy(CBI_CBR_SOURCE_PATH, tmp_path, "Occupied #001.cbr")
    cbr.with_suffix(".cbz").write_bytes(b"already-here")

    dest = predict_write_destination(cbr)

    assert dest.converts is True
    assert dest.occupied is True


def test_an_in_place_write_is_never_occupied(tmp_path: Path) -> None:
    """An archive is not its own occupant, though its path is a real file."""
    cbz = _copy(CIX_CBZ_SOURCE_PATH, tmp_path, "InPlace #001.cbz")

    dest = predict_write_destination(cbz)

    assert dest.destination.is_file()
    assert dest.occupied is False


def test_predict_does_not_open_the_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Prediction sniffs the leading bytes and stops.

    No member listing, no decompression, no schema load -- that is what
    makes a pre-pass over a whole batch affordable.
    """
    cb7 = _copy(CB7_SOURCE_PATH, tmp_path, "Cheap #001.cb7")
    calls: list[object] = []
    monkeypatch.setattr(
        Comicbox, "_to_dict", lambda _self, *a, **kw: calls.append((a, kw))
    )

    dest = predict_write_destination(cb7)

    assert dest.converts is True
    assert not calls
    assert Comicbox(cb7)._archive is None


def test_a_missing_path_raises(tmp_path: Path) -> None:
    """Construction's own error reaches the caller, who decides."""
    with pytest.raises(FileNotFoundError):
        predict_write_destination(tmp_path / "nope.cbz")


def test_a_directory_raises(tmp_path: Path) -> None:
    """A directory is not an archive."""
    with pytest.raises(IsADirectoryError):
        predict_write_destination(tmp_path)


def test_junk_bytes_raise_unsupported(tmp_path: Path) -> None:
    """A corrupt file fails at the sniff, not after a write attempt."""
    junk = tmp_path / "junk.cbz"
    junk.write_bytes(b"not an archive at all")

    with pytest.raises(UnsupportedArchiveTypeError):
        predict_write_destination(junk)
