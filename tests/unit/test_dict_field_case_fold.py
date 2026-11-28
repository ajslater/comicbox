"""
DictField folds case-variant keys by merging them, not by replacing one.

`case_insensitive_dict` kept only the last of two keys that differed only in
case, so 'Stan Lee' the Writer and 'STAN LEE' the Editor became one person
with one role, and a character's ids could vanish the same way. The merged
metadata held both spellings; the loss happened in the final dump that
`to_dict()` and the comicbox YAML/JSON writers return.
"""

from __future__ import annotations

from collections.abc import Mapping

from comicbox.box import Comicbox
from comicbox.formats import MetadataFormats
from comicbox.formats.base.fields.collection_fields import case_insensitive_dict
from comicbox.formats.comicbox.schema.yaml import ComicboxYamlSchema

_CIX = """<?xml version="1.0"?>
<ComicInfo>
  <Series>S</Series>
  <Writer>Stan Lee</Writer>
  <Characters>Spider-Man</Characters>
</ComicInfo>"""

_METRON = """<?xml version="1.0"?>
<MetronInfo>
  <Series><Name>S</Name></Series>
  <Characters><Character id="42">SPIDER-MAN</Character></Characters>
  <Credits>
    <Credit>
      <Creator>STAN LEE</Creator>
      <Roles><Role>Editor</Role></Roles>
    </Credit>
  </Credits>
</MetronInfo>"""


def test_case_variant_keys_merge_their_values() -> None:
    """Both roles survive under the first spelling."""
    folded = case_insensitive_dict(
        {
            "Stan Lee": {"roles": {"Writer": {}}},
            "STAN LEE": {"roles": {"Editor": {}}},
        }
    )
    assert folded == {"Stan Lee": {"roles": {"Writer": {}, "Editor": {}}}}


def test_case_variant_sets_union() -> None:
    """Nested sets union rather than one replacing the other."""
    folded = case_insensitive_dict(
        {"Arc": {"tags": {"a"}, "number": 1}, "ARC": {"tags": {"b"}}}
    )
    assert folded == {"Arc": {"tags": {"a", "b"}, "number": 1}}


def test_case_variant_merge_does_not_mutate_the_input() -> None:
    """The caller's nested values stay as they were."""
    first = {"roles": {"Writer": {}}}
    case_insensitive_dict({"Stan Lee": first, "STAN LEE": {"roles": {"Editor": {}}}})
    assert first == {"roles": {"Writer": {}}}


def test_case_variant_non_mappings_keep_the_later_value() -> None:
    """Values that can't merge keep the old behavior: the later pair wins."""
    assert case_insensitive_dict({"a": 1, "A": 2}) == {"A": 2}


def test_distinct_keys_are_untouched() -> None:
    """No collision, no change."""
    d = {"Stan Lee": {"roles": {"Writer": {}}}, "Jack Kirby": {}}
    assert case_insensitive_dict(d) == d


def test_schema_load_keeps_both_roles() -> None:
    """The comicbox YAML schema merges the two credits into one person."""
    loaded = ComicboxYamlSchema().load(
        {
            "comicbox": {
                "credits": {
                    "Stan Lee": {"roles": {"Writer": {}}},
                    "STAN LEE": {"roles": {"Editor": {}}},
                }
            }
        }
    )
    assert isinstance(loaded, Mapping)
    people = loaded["comicbox"]["credits"]
    assert len(people) == 1
    (credit,) = people.values()
    assert set(credit["roles"]) == {"Writer", "Editor"}


def test_single_comicinfo_keeps_both_roles() -> None:
    """One ComicInfo naming one person in two cases keeps both roles."""
    cix = """<?xml version="1.0"?><ComicInfo><Series>S</Series>
    <Writer>Stan Lee</Writer><Editor>STAN LEE</Editor></ComicInfo>"""
    with Comicbox() as car:
        car.add_metadata(cix, MetadataFormats.COMIC_INFO)
        people = car.to_dict()["comicbox"]["credits"]
    assert len(people) == 1
    (credit,) = people.values()
    assert set(credit["roles"]) == {"Writer", "Editor"}


def test_cross_source_to_dict_keeps_roles_and_ids() -> None:
    """End to end: to_dict keeps both roles and the Metron character id."""
    with Comicbox() as car:
        car.add_metadata(_CIX, MetadataFormats.COMIC_INFO)
        car.add_metadata(_METRON, MetadataFormats.METRON_INFO)
        md = car.to_dict()["comicbox"]
        yaml = car.to_string(MetadataFormats.COMICBOX_YAML)
    people = md["credits"]
    assert len(people) == 1
    (credit,) = people.values()
    assert set(credit["roles"]) == {"Writer", "Editor"}
    characters = md["characters"]
    assert len(characters) == 1
    (character,) = characters.values()
    assert character["identifiers"]["metron"]["key"] == "42"
    assert "Writer" in yaml
    assert "Editor" in yaml
