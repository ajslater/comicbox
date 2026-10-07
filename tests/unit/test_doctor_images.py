"""The doctor's Images section: what cover matching needs to hash a cover."""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING

from PIL import Image

from comicbox.doctor import images
from comicbox.doctor.context import DoctorContext
from comicbox.doctor.result import Status
from comicbox.formats.base.online import cover_hash

if TYPE_CHECKING:
    import pytest


def _without(monkeypatch: pytest.MonkeyPatch, *extensions: str) -> None:
    """Make Pillow lack the codecs for these extensions."""
    registered = dict(Image.registered_extensions())
    for extension in extensions:
        registered.pop(extension, None)
    monkeypatch.setattr(Image, "registered_extensions", lambda: registered)


def test_pillow_without_jxl_is_ok_with_a_note(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pillow's wheels have no JPEG XL, so a WARN would show on every install."""
    _without(monkeypatch, ".jxl")
    (row,) = images.check_pillow(DoctorContext())
    assert row.status is Status.OK
    assert row.detail.endswith("no jxl codec")
    assert "jpeg" in row.detail


def test_pillow_missing_core_codec_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    _without(monkeypatch, ".webp", ".jxl")
    (row,) = images.check_pillow(DoctorContext())
    assert row.status is Status.WARN
    assert row.detail.startswith("no webp codec")


def test_cover_hash_self_test_passes() -> None:
    (row,) = images.check_cover_hash(DoctorContext())
    assert row.name == "cover hash"
    assert row.status is Status.OK
    assert row.detail == "pHash self-test OK"


def test_cover_hash_crash_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(_image_bytes: bytes) -> str:
        reason = "PNG decoder is broken"
        raise ValueError(reason)

    monkeypatch.setattr(cover_hash, "compute_phash", broken)
    (row,) = images.check_cover_hash(DoctorContext())
    assert row.status is Status.ERROR
    assert "PNG decoder is broken" in row.detail
    assert "--force-reinstall comicbox" in row.fix


def test_cover_hash_wrong_answer_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A hash that runs but disagrees with imagehash would never match Metron."""
    monkeypatch.setattr(cover_hash, "compute_phash", lambda _image_bytes: "0" * 16)
    (row,) = images.check_cover_hash(DoctorContext())
    assert row.status is Status.ERROR
    assert images._CARD_PHASH in row.detail
    assert "--force-reinstall comicbox" in row.fix


def test_cover_hash_card_is_not_transposition_symmetric() -> None:
    """Shrunk to pHash's 32x32, a symmetric card could tie and flip a bit."""
    with Image.open(BytesIO(images._test_card_png())) as card:
        small = card.resize((32, 32), Image.Resampling.LANCZOS)
    assert small.transpose(Image.Transpose.TRANSPOSE).tobytes() != small.tobytes()
