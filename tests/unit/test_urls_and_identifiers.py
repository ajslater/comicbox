"""Identifiers and urls are stored apart and derived from each other."""

from argparse import Namespace

from comicbox.box import Comicbox
from comicbox.config import get_config
from comicbox.formats import MetadataFormats

_CV_KEY = "145269"
_CV_URL = f"https://comicvine.gamespot.com/c/4000-{_CV_KEY}/"
_CV_SLUG_URL = f"https://comicvine.gamespot.com/captain-science-1/4000-{_CV_KEY}/"
_UNKNOWN_URL = "https://example.com/some/comic"


def _load_yaml(yaml_str: str) -> dict:
    with Comicbox() as car:
        car.add_metadata(yaml_str, MetadataFormats.COMICBOX_YAML)
        return dict(car.to_dict().get("comicbox", {}))


def test_url_supplies_a_missing_identifier() -> None:
    """A recognized database url yields the id it contains."""
    sub_md = _load_yaml(f"""
comicbox:
  urls:
    - {_CV_URL}
""")
    assert sub_md["identifiers"]["comicvine"]["key"] == _CV_KEY


def test_identifier_supplies_a_missing_url() -> None:
    """An id yields the web url for it."""
    sub_md = _load_yaml(f"""
comicbox:
  identifiers:
    comicvine:
      key: "{_CV_KEY}"
""")
    assert sub_md["urls"] == [_CV_URL]


def test_explicit_identifier_beats_a_url_slug() -> None:
    """
    A url path must not overwrite an authoritative id.

    Several databases put a slug in the path, so the url's key is a fallback
    for files that carry only a web link, never a correction.
    """
    sub_md = _load_yaml("""
comicbox:
  identifiers:
    metron:
      key: "123495"
  urls:
    - https://metron.cloud/issue/batman-2016-0/
""")
    assert sub_md["identifiers"]["metron"]["key"] == "123495"


def test_unknown_url_is_kept_but_invents_no_identifier() -> None:
    """A url from a site comicbox doesn't know stays, as itself only."""
    sub_md = _load_yaml(f"""
comicbox:
  urls:
    - {_UNKNOWN_URL}
""")
    assert _UNKNOWN_URL in sub_md["urls"]
    assert not sub_md.get("identifiers")


def test_urls_keep_their_order_and_do_not_duplicate() -> None:
    """The file's own urls come first and a derived one is only added once."""
    sub_md = _load_yaml(f"""
comicbox:
  identifiers:
    comicvine:
      key: "{_CV_KEY}"
  urls:
    - {_CV_SLUG_URL}
    - {_UNKNOWN_URL}
""")
    assert sub_md["urls"] == [_CV_SLUG_URL, _UNKNOWN_URL, _CV_URL]


def test_identifiers_store_no_url() -> None:
    """The identifier itself never carries a url in v3."""
    sub_md = _load_yaml(f"""
comicbox:
  identifiers:
    comicvine:
      key: "{_CV_KEY}"
""")
    assert sub_md["identifiers"]["comicvine"] == {"key": _CV_KEY}


def test_notes_stamp_sees_a_url_derived_identifier() -> None:
    """
    The stamp must see identifiers derived from urls.

    The tagger stamp bakes identifier urns into notes. Computed actions all
    read one snapshot of the merged metadata, so the derivation has to land
    in that snapshot before the stamp reads it.
    """
    config = get_config(Namespace(comicbox=Namespace(write=Namespace(stamp=True))))
    with Comicbox(config=config) as car:
        car.add_metadata(
            f"comicbox:\n  urls:\n    - {_CV_URL}\n",
            MetadataFormats.COMICBOX_YAML,
        )
        notes = car.to_dict().get("comicbox", {}).get("notes") or ""
    assert f"urn:comicvine:{_CV_KEY}" in notes
