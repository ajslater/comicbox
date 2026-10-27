"""
MetronInfo v1.2 Series EndYear, Status and Summary.

MetronInfo v1.2 adds the three elements and two assertions: EndYear can't
precede StartYear, and an Ongoing series has no EndYear. Merged metadata can
break either, so the writer leaves EndYear out of the file instead of writing
one that fails validation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from loguru import logger

from comicbox.box import Comicbox
from comicbox.box.validate import validate_source
from comicbox.formats import MetadataFormats

if TYPE_CHECKING:
    from collections.abc import Iterator

_SUMMARY = "A team of heroes defends the Earth."
_METRON_XML = f"""<MetronInfo>
  <Series>
    <Name>Justice League</Name>
    <StartYear>1970</StartYear>
    <EndYear>1975</EndYear>
    <Status>Completed</Status>
    <Summary>{_SUMMARY}</Summary>
  </Series>
</MetronInfo>"""
_END_YEAR_WARNING = "MetronInfo: not writing Series EndYear"


@pytest.fixture
def warnings() -> Iterator[list[str]]:
    """Collect loguru warning messages."""
    messages: list[str] = []
    handler_id = logger.add(messages.append, level="WARNING", format="{message}")
    yield messages
    logger.remove(handler_id)


def _series_xml(body: str) -> str:
    return f"<MetronInfo><Series><Name>Foo</Name>{body}</Series></MetronInfo>"


def _read_series(xml: str) -> dict:
    with Comicbox() as car:
        car.add_metadata(xml, MetadataFormats.METRON_INFO)
        return dict(car.to_dict()["comicbox"]["series"])


def _write(metadata: str, fmt: MetadataFormats) -> str:
    with Comicbox() as car:
        car.add_metadata(metadata, fmt)
        written = car.to_string(MetadataFormats.METRON_INFO)
    assert validate_source(written, MetadataFormats.METRON_INFO)
    return written


def _write_native(series_yaml: str) -> str:
    yaml = f"comicbox:\n  series:\n    name: Foo\n{series_yaml}"
    return _write(yaml, MetadataFormats.COMICBOX_YAML)


def test_read() -> None:
    """Each element lands in its series field."""
    series = _read_series(_METRON_XML)
    assert series["end_year"] == 1975
    assert series["status"] == "Completed"
    assert series["summary"] == _SUMMARY


def test_write_validates() -> None:
    """All three are written back and pass the v1.2 XSD."""
    written = _write(_METRON_XML, MetadataFormats.METRON_INFO)
    assert "<EndYear>1975</EndYear>" in written
    assert "<Status>Completed</Status>" in written
    assert f"<Summary>{_SUMMARY}</Summary>" in written


def test_status_is_read_loosely_and_written_canonically() -> None:
    """Lowercase is invalid XSD but reads, and writes as the canonical label."""
    xml = _series_xml("<Status>ongoing</Status>")
    assert _read_series(xml)["status"] == "Ongoing"
    assert "<Status>Ongoing</Status>" in _write(xml, MetadataFormats.METRON_INFO)


def test_unknown_status_is_dropped_alone() -> None:
    """A status outside the vocabulary costs only that key."""
    series = _read_series(
        _series_xml("<StartYear>1970</StartYear><Status>Unknown</Status>")
    )
    assert "status" not in series
    assert series["name"] == "Foo"
    assert series["start_year"] == 1970


def test_zoned_year_reads_as_its_year() -> None:
    """A gYear may carry a timezone; the year survives."""
    assert (
        _read_series(_series_xml("<EndYear>1975+05:00</EndYear>"))["end_year"] == 1975
    )


def test_ongoing_series_writes_no_end_year(warnings: list[str]) -> None:
    """The assert `not(Status = 'Ongoing' and EndYear)` is honored."""
    written = _write_native("    status: Ongoing\n    end_year: 1975\n")
    assert "<Status>Ongoing</Status>" in written
    assert "EndYear" not in written
    assert any(msg.startswith(_END_YEAR_WARNING) for msg in warnings)


def test_end_year_before_start_year_is_not_written(warnings: list[str]) -> None:
    """The assert EndYear >= StartYear is honored."""
    written = _write_native("    start_year: 1975\n    end_year: 1970\n")
    assert "<StartYear>1975</StartYear>" in written
    assert "EndYear" not in written
    assert any(msg.startswith(_END_YEAR_WARNING) for msg in warnings)


@pytest.mark.parametrize(
    "series_yaml",
    [
        "    end_year: 1970\n",
        "    start_year: 1970\n    end_year: 1970\n",
        "    status: Completed\n    start_year: 1970\n    end_year: 1975\n",
    ],
)
def test_valid_end_year_is_written(series_yaml: str, warnings: list[str]) -> None:
    """EndYear alone, equal to StartYear, or after it with an ended status."""
    written = _write_native(series_yaml)
    assert "<EndYear>" in written
    assert not any(msg.startswith(_END_YEAR_WARNING) for msg in warnings)
