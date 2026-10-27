"""Series year range, status and summary in the comicbox native formats."""

from __future__ import annotations

from typing import Any

import pytest

from comicbox.box import Comicbox
from comicbox.enums.comicbox import SeriesStatusEnum
from comicbox.formats import MetadataFormats
from comicbox.formats.base.schemas.cache import get_schema
from comicbox.formats.comicbox.schema import ComicboxSchemaMixin
from comicbox.formats.comicbox.schema.json_schema import ComicboxJsonSchema
from comicbox.formats.comicbox.schema.yaml import ComicboxYamlSchema

_ROOT = ComicboxSchemaMixin.ROOT_TAG
_SERIES = {
    "name": "Captain Science",
    "start_year": 1950,
    "end_year": 1951,
    "status": "Cancelled",
    "summary": "A short run.",
}
_SCHEMAS = (ComicboxYamlSchema, ComicboxJsonSchema)


def _series(loaded: object) -> dict[str, Any]:
    """Narrow a schema load result to its series block."""
    assert isinstance(loaded, dict)
    return loaded[_ROOT]["series"]


@pytest.mark.parametrize("schema_class", _SCHEMAS)
def test_series_fields_round_trip(
    schema_class: type[ComicboxYamlSchema | ComicboxJsonSchema],
) -> None:
    """Every new series field survives a dump and reload."""
    schema = get_schema(schema_class)
    loaded = schema.load({_ROOT: {"series": _SERIES}})
    assert isinstance(loaded, dict)
    series = _series(loaded)
    assert series["status"] == SeriesStatusEnum.CANCELLED
    assert {key: series[key] for key in ("start_year", "end_year", "summary")} == {
        "start_year": 1950,
        "end_year": 1951,
        "summary": "A short run.",
    }

    text = schema.dumps(loaded)
    assert "Cancelled" in text
    assert _series(schema.loads(text)) == series


@pytest.mark.parametrize("schema_class", _SCHEMAS)
def test_series_status_is_matched_loosely(
    schema_class: type[ComicboxYamlSchema | ComicboxJsonSchema],
) -> None:
    schema = get_schema(schema_class)
    loaded = schema.load({_ROOT: {"series": {"name": "S", "status": "ongoing"}}})
    assert _series(loaded)["status"] == SeriesStatusEnum.ONGOING


@pytest.mark.parametrize("schema_class", _SCHEMAS)
def test_unknown_series_status_is_dropped(
    schema_class: type[ComicboxYamlSchema | ComicboxJsonSchema],
) -> None:
    """A status outside the enum is dropped, not loaded raw."""
    schema = get_schema(schema_class)
    loaded = schema.load({_ROOT: {"series": {"name": "S", "status": "Rebooted"}}})
    assert _series(loaded) == {"name": "S"}


_SERIES_YAML = f"""
{_ROOT}:
  series:
    name: Captain Science
    start_year: 1950
    end_year: 1951
    status: Cancelled
    summary: A short run.
"""


def test_series_fields_survive_the_metadata_pipeline() -> None:
    """The merged metadata keeps them, and MetronInfo v1.2 carries them all."""
    with Comicbox() as car:
        car.add_metadata(_SERIES_YAML, MetadataFormats.COMICBOX_YAML)
        series = car.get_internal_metadata()[_ROOT]["series"]
        metron_info = car.to_string(MetadataFormats.METRON_INFO)

    assert series["end_year"] == 1951
    assert series["status"] == SeriesStatusEnum.CANCELLED
    assert series["summary"] == "A short run."
    assert "<StartYear>1950</StartYear>" in metron_info
    assert "<EndYear>1951</EndYear>" in metron_info
    assert "<Status>Cancelled</Status>" in metron_info
    assert "<Summary>A short run.</Summary>" in metron_info
