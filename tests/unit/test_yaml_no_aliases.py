"""Comic YAML is written without aliases, and read as before (B11)."""

from datetime import date

from comicbox.box import Comicbox
from comicbox.formats import MetadataFormats

_DATE = date(2006, 7, 4)


def test_one_object_written_twice_is_written_twice() -> None:
    """One date for cover and store came out as &id001 and *id001."""
    metadata = {
        "comicbox": {
            "series": {"name": "X"},
            "date": {"cover_date": _DATE, "store_date": _DATE},
        }
    }
    with Comicbox(metadata=metadata) as box:
        text = box.to_string(MetadataFormats.COMICBOX_YAML)
    assert "&" not in text
    assert "*" not in text
    assert text.count("2006-07-04") == 2


def test_a_file_with_aliases_still_reads() -> None:
    text = (
        "comicbox:\n  series: {name: X}\n  date:\n"
        "    cover_date: &d 2006-07-04\n    store_date: *d\n"
    )
    with Comicbox(metadata=text, fmt=MetadataFormats.COMICBOX_YAML) as box:
        dates = box.to_dict()["comicbox"]["date"]
    assert dates["cover_date"] == dates["store_date"] == _DATE
