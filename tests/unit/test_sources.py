"""Tests for ComicboxSources._get_source_config_metadata."""

from argparse import Namespace

from comicbox.box import Comicbox
from comicbox.formats import MetadataFormats

_MD = {"series": {"name": "Test"}, "issue": {"number": 1}}


def _sources(
    *,
    metadata: dict | None = None,
    metadata_format: str | None = None,
    read: list | None = None,
):
    general_kwargs: dict = {}
    if metadata is not None:
        general_kwargs["metadata"] = metadata
    if metadata_format is not None:
        general_kwargs["metadata_format"] = metadata_format
    cb_kwargs: dict = {}
    if general_kwargs:
        cb_kwargs["general"] = Namespace(**general_kwargs)
    if read is not None:
        cb_kwargs["read"] = Namespace(formats=read)
    cb = Comicbox(config=Namespace(comicbox=Namespace(**cb_kwargs)))
    return cb._get_source_config_metadata()


def test_format_in_read_returns_source() -> None:
    """metadata_format hint in read formats: returns one SourceData with that fmt."""
    src = _sources(metadata=_MD, metadata_format="COMIC_INFO", read=["cix"])
    assert len(src) == 1
    assert src[0].fmt is MetadataFormats.COMIC_INFO


def test_no_format_returns_unhinted_source() -> None:
    """No metadata_format: returns one SourceData with fmt=None for guessing."""
    src = _sources(metadata=_MD, read=["cix"])
    assert len(src) == 1
    assert src[0].fmt is None


def test_format_not_in_read_skips() -> None:
    """metadata_format hint outside read formats: skip — caller doesn't want it."""
    src = _sources(metadata=_MD, metadata_format="COMIC_INFO", read=["cbi"])
    assert src == []


def test_invalid_format_skips() -> None:
    """Bogus metadata_format: log + skip rather than raise."""
    src = _sources(metadata=_MD, metadata_format="NONSENSE", read=["cix"])
    assert src == []


def test_no_metadata_returns_empty() -> None:
    """No api metadata: nothing to source."""
    src = _sources(read=["cix"])
    assert src == []
