"""
MetronInfo writes only what its shipped XSD allows.

IssueCount and VolumeCount are xs:positiveInteger and Price's country is
required. A ComicInfo Count of 0, a comicbox volume_count of 0 and a CoMet
price, which has no country, all wrote files that failed the XSD.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

from comicbox.box import Comicbox
from comicbox.box.validate import validate_source
from comicbox.formats import MetadataFormats
from tests.const import TEST_METADATA_DIR

if TYPE_CHECKING:
    from pathlib import Path


def _write(source: str, fmt: MetadataFormats) -> str:
    with Comicbox() as car:
        car.add_metadata(source, fmt)
        return car.to_string(MetadataFormats.METRON_INFO)


def test_comicinfo_zero_count_is_not_written() -> None:
    """A ComicInfo Count of 0 writes no IssueCount, and the file validates."""
    xml = (
        "<ComicInfo><Series>Foo</Series><Number>1</Number><Count>0</Count></ComicInfo>"
    )
    written = _write(xml, MetadataFormats.COMIC_INFO)
    assert "IssueCount" not in written
    assert validate_source(written, MetadataFormats.METRON_INFO)


def test_zero_volume_count_is_not_written() -> None:
    """A comicbox volume_count of 0 writes no VolumeCount, and the file validates."""
    yaml = "comicbox:\n  series:\n    name: Foo\n    volume_count: 0\n"
    written = _write(yaml, MetadataFormats.COMICBOX_YAML)
    assert "VolumeCount" not in written
    assert validate_source(written, MetadataFormats.METRON_INFO)


def test_positive_counts_are_written() -> None:
    """Real counts still reach the file."""
    yaml = (
        "comicbox:\n  series:\n    name: Foo\n    volume_count: 3\n"
        "  volume:\n    issue_count: 12\n"
    )
    written = _write(yaml, MetadataFormats.COMICBOX_YAML)
    assert "<VolumeCount>3</VolumeCount>" in written
    assert "<IssueCount>12</IssueCount>" in written
    assert validate_source(written, MetadataFormats.METRON_INFO)


def test_countryless_price_is_skipped() -> None:
    """Only the price with a country is written."""
    yaml = (
        'comicbox:\n  series:\n    name: Foo\n  prices:\n    "": 1.99\n    US: 2.50\n'
    )
    written = _write(yaml, MetadataFormats.COMICBOX_YAML)
    assert '<Price country="US">2.50</Price>' in written
    assert "1.99" not in written
    assert validate_source(written, MetadataFormats.METRON_INFO)


def test_comet_fixture_converts_to_valid_metroninfo(tmp_path: Path) -> None:
    """The CoMet fixture, whose price has no country, converts to a valid file."""
    comet_path = tmp_path / "comet.xml"
    shutil.copy(TEST_METADATA_DIR / "comet.xml", comet_path)
    written = _write(comet_path.read_text(), MetadataFormats.COMET)
    assert validate_source(written, MetadataFormats.METRON_INFO)
