"""
ComicInfo's Alternate tags name a crossover arc.

ComicInfo v1.0 had no StoryArc, so libraries tagged before v2.0 recorded
crossovers in AlternateSeries and AlternateNumber, which is what ComicRack
documented them for and what Komga and Kavita still read them as. Comicbox
finds those arcs and writes arcs back only to StoryArc, the tag that exists
for this today.
"""

from typing import Any

from comicbox.formats.comic_info.schema import ComicInfoSchema
from comicbox.formats.comic_info.transform import ComicInfoTransform

_CIX = ComicInfoTransform(None)


def _to_cb(native: dict[str, Any]) -> dict:
    loaded: dict = ComicInfoSchema().load({"ComicInfo": native})  # pyright: ignore[reportAssignmentType]
    return dict(_CIX.to_comicbox(loaded).get("comicbox", {}))


def _from_cb(sub_md: dict[str, Any]) -> dict:
    return dict(_CIX.from_comicbox({"comicbox": sub_md}).get("ComicInfo", {}))


def test_alternate_series_reads_as_an_arc() -> None:
    """The crossover the old tags name becomes an arc."""
    sub_md = _to_cb({"AlternateSeries": "Civil War", "AlternateNumber": "3"})
    assert sub_md["arcs"]["Civil War"] == {"number": 3}


def test_alternate_series_is_not_a_reprint() -> None:
    """It is a reading order position, not another edition of the book."""
    sub_md = _to_cb({"AlternateSeries": "Civil War", "AlternateNumber": "3"})
    assert not sub_md.get("reprints")


def test_alternates_join_the_story_arcs() -> None:
    """Both tag pairs feed the one arcs field."""
    sub_md = _to_cb(
        {
            "StoryArc": "House of M,Decimation",
            "StoryArcNumber": "1,2",
            "AlternateSeries": "Civil War",
            "AlternateNumber": "3",
        }
    )
    assert sub_md["arcs"] == {
        "House of M": {"number": 1},
        "Decimation": {"number": 2},
        "Civil War": {"number": 3},
    }


def test_story_arc_wins_a_name_collision() -> None:
    """The modern tag is authoritative when both name the same arc."""
    sub_md = _to_cb(
        {
            "StoryArc": "Civil War",
            "StoryArcNumber": "1",
            "AlternateSeries": "Civil War",
            "AlternateNumber": "3",
        }
    )
    assert sub_md["arcs"] == {"Civil War": {"number": 1}}


def test_alternate_series_without_a_number() -> None:
    """An arc with no position is still an arc."""
    sub_md = _to_cb({"AlternateSeries": "Civil War"})
    assert sub_md["arcs"] == {"Civil War": {}}


def test_non_numeric_alternate_number_is_dropped() -> None:
    """A position that isn't a number says nothing about order."""
    sub_md = _to_cb({"AlternateSeries": "Civil War", "AlternateNumber": "one"})
    assert sub_md["arcs"] == {"Civil War": {}}


def test_arcs_write_only_to_story_arc() -> None:
    """Comicbox writes the tags that exist for arcs today."""
    comicinfo = _from_cb({"arcs": {"Civil War": {"number": 3}}})
    assert comicinfo["StoryArc"] == ["Civil War"]
    assert comicinfo["StoryArcNumber"] == [3]
    assert not comicinfo.get("AlternateSeries")
    assert not comicinfo.get("AlternateNumber")
