"""
`ComicboxValidate.validate` tests — the `--validate` action.

`validate()` is one of the four `_CONFIG_ACTIONS` `Comicbox.run()`
dispatches, and it's the only one that ends the process: a failing
source exits 1 so `comicbox --validate` is usable as a CI gate. These
tests cover the gate, the per-source loop, and both terminal outcomes.

`tests/test_validate_testfiles.py` exercises `validate_source` against
the real fixture corpus; this module covers the box method around it.
"""

from __future__ import annotations

from argparse import Namespace
from typing import TYPE_CHECKING

import pytest
from loguru import logger

from comicbox.box import Comicbox
from comicbox.box.validate import validate_source
from comicbox.exceptions import MetadataError
from comicbox.formats import MetadataFormats
from comicbox.formats.sources import MetadataSources

if TYPE_CHECKING:
    from collections.abc import Iterator

VALID_CIX = (
    '<?xml version="1.0" encoding="utf-8"?>'
    "<ComicInfo><Series>Captain Science</Series><Number>1</Number></ComicInfo>"
)
INVALID_CIX = (
    '<?xml version="1.0" encoding="utf-8"?>'
    "<ComicInfo><NotAComicInfoField>x</NotAComicInfoField></ComicInfo>"
)


@pytest.fixture
def records() -> Iterator[list[tuple[str, str]]]:
    """Capture (level, message) for every log record."""
    captured: list[tuple[str, str]] = []
    handler_id = logger.add(
        lambda m: captured.append((m.record["level"].name, m.record["message"])),
        level="TRACE",
    )
    try:
        yield captured
    finally:
        logger.remove(handler_id)


def _build_cb(
    metadata: str | None = None,
    fmt: MetadataFormats | None = None,
    *,
    validate: bool = True,
) -> Comicbox:
    args = Namespace(comicbox=Namespace(print=Namespace(validate=validate)))
    cb = Comicbox(config=args)
    if metadata is not None:
        cb.add_source(MetadataSources.API, metadata, fmt=fmt)
    return cb


def _levels(records: list[tuple[str, str]], level: str) -> list[str]:
    return [message for name, message in records if name == level]


# --- the --validate gate ----------------------------------------------------


def test_validate_is_a_noop_when_not_requested(
    records: list[tuple[str, str]],
) -> None:
    """Without `--validate`, the action neither validates nor announces."""
    _build_cb(INVALID_CIX, MetadataFormats.COMIC_INFO, validate=False).validate()
    assert records == []


# --- success ----------------------------------------------------------------


def test_valid_source_succeeds(records: list[tuple[str, str]]) -> None:
    _build_cb(VALID_CIX, MetadataFormats.COMIC_INFO).validate()
    assert "ComicInfo: data validated" in _levels(records, "INFO")
    assert _levels(records, "SUCCESS") == ["Metadata validation succeeded"]


def test_no_sources_succeeds(records: list[tuple[str, str]]) -> None:
    """Nothing to validate is a pass, not a failure."""
    _build_cb().validate()
    assert _levels(records, "SUCCESS") == ["Metadata validation succeeded"]


def test_format_without_a_validator_passes(records: list[tuple[str, str]]) -> None:
    """PDF/online formats register `validator=None` and are waved through."""
    _build_cb('{"format": "MuPDF"}', MetadataFormats.PDF).validate()
    assert any("no validator available" in m for m in _levels(records, "WARNING"))
    assert _levels(records, "SUCCESS") == ["Metadata validation succeeded"]


# --- failure ----------------------------------------------------------------


def test_invalid_source_exits_one(records: list[tuple[str, str]]) -> None:
    """The CI-gate contract: a schema violation exits 1."""
    cb = _build_cb(INVALID_CIX, MetadataFormats.COMIC_INFO)
    with pytest.raises(SystemExit) as exc_info:
        cb.validate()
    assert exc_info.value.code == 1
    warnings = _levels(records, "WARNING")
    assert any("ComicInfo: failed validation" in m for m in warnings)
    assert _levels(records, "ERROR") == ["Metadata validation failed"]
    assert _levels(records, "SUCCESS") == []


def test_one_bad_source_among_good_ones_still_exits(
    records: list[tuple[str, str]],
) -> None:
    """`validated &=` accumulates: a later pass can't clear an earlier fail."""
    cb = _build_cb(INVALID_CIX, MetadataFormats.COMIC_INFO)
    cb.add_source(MetadataSources.API, VALID_CIX, fmt=MetadataFormats.COMIC_INFO)
    with pytest.raises(SystemExit) as exc_info:
        cb.validate()
    assert exc_info.value.code == 1
    # Both sources were visited, not just the failing one.
    assert "ComicInfo: data validated" in _levels(records, "INFO")


def test_validate_runs_through_the_run_action_dispatch() -> None:
    """`--validate` reaches `validate()` via `Comicbox.run()`'s action map."""
    cb = _build_cb(INVALID_CIX, MetadataFormats.COMIC_INFO)
    with pytest.raises(SystemExit) as exc_info:
        cb.run()
    assert exc_info.value.code == 1


# --- validate_source edges --------------------------------------------------


def test_validate_source_without_a_format_raises() -> None:
    """An unguessable source is an error, not a silent pass."""
    with pytest.raises(MetadataError):
        validate_source(VALID_CIX)


def test_validate_source_guesses_the_format_from_a_path() -> None:
    from tests.const import TEST_METADATA_DIR

    assert validate_source(TEST_METADATA_DIR / "comicinfo-write.xml") is True


def test_validate_source_reports_a_bad_document() -> None:
    assert validate_source(INVALID_CIX, fmt=MetadataFormats.COMIC_INFO) is False


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
