"""
MetronInfo writes one primary id source for <IDS>, <URLs> and every tag `id`.

A tag `id` attribute names no database of its own. The reader files it under
the source of the flagged <ID primary="true">, else the flagged <URL>, else
Metron. The writer used to flag the best ranked <ID> while writing the tag ids
of `primary_id_source`, or of Metron when that was unset, so a file with
Metron tag ids and only a Comic Vine issue id came back with every tag id
relabeled as Comic Vine, and Comic Vine tag ids were never written at all.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any, cast

from comicbox.box import Comicbox
from comicbox.box.validate import validate_source
from comicbox.formats import MetadataFormats
from tests.const import TEST_METADATA_DIR

NO_PRIMARY_FN = "metroninfo-no-primary-id.xml"
CV_ONLY_YAML = """\
comicbox:
  identifiers:
    comicvine:
      key: "145269"
  publisher:
    name: Youthful Adventure Stories
    identifiers:
      comicvine:
        key: "11"
  series:
    name: Captain Science
    identifiers:
      comicvine:
        key: "2222"
  characters:
    Captain Science:
      identifiers:
        comicvine:
          key: "3333"
  credits:
    Joe Orlando:
      identifiers:
        comicvine:
          key: "9999"
      roles:
        Writer: {}
"""
METRON_CHARACTER_CV_ISSUE_YAML = """\
comicbox:
  identifiers:
    comicvine:
      key: "145269"
  series:
    name: Captain Science
  characters:
    Captain Science:
      identifiers:
        metron:
          key: "3333"
"""


def _read(source: str, fmt: MetadataFormats) -> dict[str, Any]:
    with Comicbox() as car:
        car.add_metadata(source, fmt)
        return dict(car.to_dict()["comicbox"])


def _write(source: str, fmt: MetadataFormats) -> str:
    with Comicbox() as car:
        car.add_metadata(source, fmt)
        return car.to_string(MetadataFormats.METRON_INFO)


def _children(node: Any, path: str) -> Iterator[tuple[str, Any]]:
    if isinstance(node, Mapping):
        return (
            (f"{path}.{key}" if path else str(key), value)
            for key, value in node.items()
        )
    if isinstance(node, list):
        return ((f"{path}[{index}]", item) for index, item in enumerate(node))
    return iter(())


def _identifiers(node: Any, path: str = "") -> Iterator[tuple[str, str, str]]:
    """Yield (path, source, key) for every identifier in the tree."""
    identifiers = cast(
        "Mapping[str, Mapping[str, str]]",
        node.get("identifiers") or {} if isinstance(node, Mapping) else {},
    )
    for id_source, identifier in identifiers.items():
        yield path, id_source, identifier.get("key", "")
    for child_path, child in _children(node, path):
        if not child_path.endswith(".identifiers"):
            yield from _identifiers(child, child_path)


def test_round_trip_keeps_every_tag_id_source() -> None:
    """Metron tag ids beside a lone Comic Vine issue id come back as Metron ids."""
    xml = (TEST_METADATA_DIR / NO_PRIMARY_FN).read_text()
    before = _read(xml, MetadataFormats.METRON_INFO)
    written = _write(xml, MetadataFormats.METRON_INFO)
    after = _read(written, MetadataFormats.METRON_INFO)
    before_ids = sorted(_identifiers(before))
    # Guard against the walker finding nothing.
    assert ("publisher", "metron", "11") in before_ids
    assert sorted(_identifiers(after)) == before_ids
    assert after.get("primary_id_source") == before.get("primary_id_source")
    assert validate_source(written, MetadataFormats.METRON_INFO)


def test_comicvine_only_tag_ids_are_written() -> None:
    """With only Comic Vine ids, Comic Vine is primary and its tag ids are written."""
    written = _write(CV_ONLY_YAML, MetadataFormats.COMICBOX_YAML)
    assert '<ID primary="true" source="Comic Vine">145269</ID>' in written
    assert '<Publisher id="11">' in written
    assert '<Series id="2222"' in written
    assert '<Character id="3333">' in written
    assert '<Creator id="9999">' in written
    assert validate_source(written, MetadataFormats.METRON_INFO)
    after = _read(written, MetadataFormats.METRON_INFO)
    assert sorted(_identifiers(after)) == sorted(
        _identifiers(_read(CV_ONLY_YAML, MetadataFormats.COMICBOX_YAML))
    )


def test_metron_tag_id_is_not_relabeled_comicvine() -> None:
    """
    A Metron character id beside only a Comic Vine issue id stays Metron.

    Metron is the format's default source, so the writer flags no <ID> primary
    and the bare tag id reads back as Metron's.
    """
    written = _write(METRON_CHARACTER_CV_ISSUE_YAML, MetadataFormats.COMICBOX_YAML)
    assert 'primary="true"' not in written
    assert '<Character id="3333">' in written
    assert validate_source(written, MetadataFormats.METRON_INFO)
    after = _read(written, MetadataFormats.METRON_INFO)
    character = after["characters"]["Captain Science"]
    assert character["identifiers"] == {"metron": {"key": "3333"}}
    assert after["identifiers"]["comicvine"]["key"] == "145269"


def test_explicit_primary_id_source_wins() -> None:
    """A stated primary_id_source among the issue ids is the one flagged."""
    yaml = (
        "comicbox:\n  primary_id_source: comicvine\n  identifiers:\n"
        '    comicvine:\n      key: "1"\n    metron:\n      key: "2"\n'
        "  publisher:\n    name: P\n    identifiers:\n"
        '      comicvine:\n        key: "11"\n      metron:\n        key: "22"\n'
    )
    written = _write(yaml, MetadataFormats.COMICBOX_YAML)
    assert '<ID primary="true" source="Comic Vine">1</ID>' in written
    assert '<Publisher id="11">' in written


BOTH_ISSUE_IDS = (
    "comicbox:\n  identifiers:\n"
    '    comicvine:\n      key: "1"\n    metron:\n      key: "2"\n'
)


def test_most_tag_ids_source_is_primary() -> None:
    """
    With Metron and Comic Vine issue ids and only Comic Vine tag ids, Comic Vine wins.

    Ranking alone picked Metron, so the Comic Vine tag ids were dropped.
    """
    yaml = (
        BOTH_ISSUE_IDS + "  publisher:\n    name: P\n    identifiers:\n"
        '      comicvine:\n        key: "11"\n'
        "  series:\n    name: S\n    identifiers:\n"
        '      comicvine:\n        key: "22"\n'
    )
    written = _write(yaml, MetadataFormats.COMICBOX_YAML)
    assert '<ID primary="true" source="Comic Vine">1</ID>' in written
    assert '<Publisher id="11">' in written
    assert '<Series id="22"' in written
    assert validate_source(written, MetadataFormats.METRON_INFO)
    after = _read(written, MetadataFormats.METRON_INFO)
    assert after["publisher"]["identifiers"] == {"comicvine": {"key": "11"}}
    assert after["series"]["identifiers"] == {"comicvine": {"key": "22"}}


def test_most_tag_ids_majority_beats_rank() -> None:
    """Two Comic Vine tag ids beat one Metron tag id; the Metron one is lost."""
    yaml = (
        BOTH_ISSUE_IDS + "  publisher:\n    name: P\n    identifiers:\n"
        '      comicvine:\n        key: "11"\n'
        "  series:\n    name: S\n    identifiers:\n"
        '      comicvine:\n        key: "22"\n'
        "  characters:\n    C:\n      identifiers:\n"
        '        metron:\n          key: "33"\n'
    )
    written = _write(yaml, MetadataFormats.COMICBOX_YAML)
    assert '<ID primary="true" source="Comic Vine">1</ID>' in written
    assert '<Publisher id="11">' in written
    assert '<Character id="33">' not in written
    assert validate_source(written, MetadataFormats.METRON_INFO)


def test_most_tag_ids_tie_goes_to_rank() -> None:
    """One Metron and one Comic Vine tag id: the better ranked Metron wins."""
    yaml = (
        BOTH_ISSUE_IDS + "  publisher:\n    name: P\n    identifiers:\n"
        '      comicvine:\n        key: "11"\n'
        "  series:\n    name: S\n    identifiers:\n"
        '      metron:\n        key: "22"\n'
    )
    written = _write(yaml, MetadataFormats.COMICBOX_YAML)
    assert '<ID primary="true" source="Metron">2</ID>' in written
    assert '<Series id="22"' in written
    assert '<Publisher id="11">' not in written
    assert validate_source(written, MetadataFormats.METRON_INFO)


def test_no_tag_ids_best_ranked_is_primary() -> None:
    """With no tag ids, the best ranked issue id source is primary."""
    written = _write(
        BOTH_ISSUE_IDS + "  series:\n    name: S\n", MetadataFormats.COMICBOX_YAML
    )
    assert '<ID primary="true" source="Metron">2</ID>' in written
    assert validate_source(written, MetadataFormats.METRON_INFO)
