"""
MetronInfo tag `id` attributes when the file names no primary id source.

A MetronInfo file may hang an `id` attribute on Publisher, Series, Arc,
Universe, Creator, Role, Story, Reprint and AlternativeName. Which database
those ids belong to is only stated indirectly, by whichever <ID> or <URL> the
file marks primary. When nothing is marked -- or the primary <URL> points at a
site comicbox doesn't recognize -- the transforms fall back to a default
source.

That fallback was dead. The multi-source `values` dict the spec layer feeds
these functions emitted an explicit ``None`` for every missing source, so
``values.get(SCOPE_PRIMARY_SOURCE, DEFAULT_ID_SOURCE)`` returned ``None``
rather than the default: ``.get`` only substitutes when the key is *absent*.
Every id was then filed under a ``None`` key and dropped by schema load.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from types import MappingProxyType
from typing import Any

import pytest
from glom import glom

from comicbox.enums.comicbox import IdSources
from comicbox.formats.comicbox.schema import IDENTIFIERS_KEY
from comicbox.formats.metron_info.transform import MetronInfoTransform
from comicbox.identifiers import ID_KEY_KEY
from tests.const import TEST_METADATA_DIR

NO_PRIMARY_FN = "metroninfo-no-primary-id.xml"
METRON = IdSources.METRON.value


def _load_fixture(transform: MetronInfoTransform) -> dict[str, Any]:
    """Parse the fixture with the MetronInfo schema."""
    xml = (TEST_METADATA_DIR / NO_PRIMARY_FN).read_text()
    loaded: dict[str, Any] = transform.SCHEMA_CLASS().loads(xml)  # pyright: ignore[reportAssignmentType]
    return dict(loaded)


def _to_comicbox() -> dict[str, Any]:
    transform = MetronInfoTransform()
    loaded = _load_fixture(transform)
    return dict(dict(transform.to_comicbox(loaded))["comicbox"])


def _raw_glom() -> dict[str, Any]:
    """Return the transform output before schema load, where None keys appeared."""
    transform = MetronInfoTransform()
    loaded = _load_fixture(transform)
    return glom(loaded, dict(transform.SPECS_TO))["comicbox"]


def test_fixture_names_no_primary_id_source() -> None:
    """The fixture has to keep provoking the fallback, or it proves nothing."""
    assert _to_comicbox().get("primary_id_source") is None


def _id_source_keys(node: Any) -> Iterator[Any]:
    """Yield every id source key under every `identifiers` dict in the tree."""
    if isinstance(node, Mapping):
        for key, value in node.items():
            if key == IDENTIFIERS_KEY and isinstance(value, Mapping):
                yield from value
            yield from _id_source_keys(value)
    elif isinstance(node, list):
        for item in node:
            yield from _id_source_keys(item)


def test_no_identifier_is_keyed_by_none() -> None:
    """A None id source key is the bug's signature. It must appear nowhere."""
    id_source_keys = list(_id_source_keys(_raw_glom()))
    # Guard against the walker silently finding nothing to check.
    assert id_source_keys
    assert None not in id_source_keys


@pytest.mark.parametrize(
    ("keypath", "id_key"),
    [
        ("publisher", "11"),
        ("imprint", "222"),
        ("series", "2222"),
        ("arcs.Captain Arc", "7777"),
        ("universes.Mirror", "8888"),
        ("credits.Joe Orlando", "9999"),
        ("credits.Joe Orlando.roles.Writer", "1111"),
        ("stories.Captain Lost", "5555"),
    ],
)
def test_tag_id_attribute_survives_and_is_attributed_to_metron(
    keypath: str, id_key: str
) -> None:
    """Each tag `id` lands under the metron source, not None and not comicvine."""
    obj = glom(_to_comicbox(), keypath)
    identifiers = obj[IDENTIFIERS_KEY]
    assert set(identifiers) == {METRON}
    assert identifiers[METRON][ID_KEY_KEY] == id_key


def test_reprint_id_attribute_survives() -> None:
    reprints = _to_comicbox()["reprints"]
    assert len(reprints) == 1
    identifiers = reprints[0][IDENTIFIERS_KEY]
    assert identifiers == {METRON: {ID_KEY_KEY: "4444"}}


def test_alternative_name_id_attribute_survives() -> None:
    alternative_names = _to_comicbox()["series"]["alternative_names"]
    assert len(alternative_names) == 1
    identifiers = alternative_names[0][IDENTIFIERS_KEY]
    assert identifiers == {METRON: {ID_KEY_KEY: "3333"}}


def test_sourced_id_tag_keeps_its_own_source() -> None:
    """The fallback must not overwrite an <ID> that names its own database."""
    identifiers = _to_comicbox()[IDENTIFIERS_KEY]
    assert identifiers[IdSources.COMICVINE.value][ID_KEY_KEY] == "145269"


def test_default_id_source_is_metron_not_comicvine() -> None:
    """
    MetronInfo's bare ids belong to Metron, the database that writes the format.

    Two different DEFAULT_ID_SOURCE constants used to be imported across these
    modules: the Metron one, and comicbox.identifiers' COMICVINE one. A fixed
    fallback reading the wrong constant would file Metron's ids under ComicVine
    and mint ComicVine urls that 404.
    """
    from comicbox.formats.metron_info.transform.const import (
        DEFAULT_ID_SOURCE,
        DEFAULT_ID_SOURCE_STR,
    )

    assert DEFAULT_ID_SOURCE is IdSources.METRON
    # The identifier dicts are keyed by the source *string*. An enum member
    # here reads back as "IdSources.METRON" and drops out on load.
    assert DEFAULT_ID_SOURCE_STR == METRON
    assert isinstance(DEFAULT_ID_SOURCE_STR, str)


def test_roundtrip_writes_the_id_attributes_back() -> None:
    """Read then write: the ids have to reappear as `id` attributes."""
    transform = MetronInfoTransform()
    comicbox_data = MappingProxyType({"comicbox": _to_comicbox()})
    metron = dict(transform.from_comicbox(comicbox_data))["MetronInfo"]
    assert metron["Publisher"]["@id"] == "11"
    assert metron["Publisher"]["Imprint"]["@id"] == "222"
    assert metron["Series"]["@id"] == "2222"
