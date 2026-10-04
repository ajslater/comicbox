"""The doctor's Images section: what cover matching needs to hash a cover."""

from __future__ import annotations

import sys
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


def test_phash_smoke_test_passes() -> None:
    (row,) = images.check_imagehash(DoctorContext())
    assert row.status is Status.OK
    assert row.detail == "phash smoke test OK"


def test_phash_failure_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(_image_bytes: bytes) -> str:
        reason = "scipy.fft is broken"
        raise ValueError(reason)

    monkeypatch.setattr(cover_hash, "compute_phash", broken)
    (row,) = images.check_imagehash(DoctorContext())
    assert row.status is Status.ERROR
    assert "scipy.fft is broken" in row.detail


def test_imagehash_import_error_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "imagehash", None)
    (row,) = images.check_imagehash(DoctorContext())
    assert row.status is Status.MISSING
    assert row.detail.startswith("can't import imagehash")
