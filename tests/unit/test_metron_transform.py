"""MetronApiTransform field-mapping tests."""

from __future__ import annotations

from comicbox.transforms.metron_api import MetronApiTransform


def _sample_issue_dict() -> dict:
    """Mokkari `Issue.model_dump(mode='json')` shape, abbreviated for test."""
    return {
        "metron_api": {
            "id": 42,
            "number": "5",
            "cover_date": "2020-04-01",
            "store_date": "2020-04-15",
            "image": "https://static.metron.cloud/media/issue/2020/04/01/foo-5.jpg",
            "cover_hash": "abcdef0123456789",
            "modified": "2020-04-02T12:00:00Z",
            "page_count": 24,
            "desc": "Some description.",
            "collection_title": "Foo Comics #5",
            "publisher": {"id": 1, "name": "Quality Comics"},
            "series": {
                "id": 100,
                "name": "Foo Comics",
                "year_began": 2018,
                "volume": 1,
            },
        }
    }


def test_to_comicbox_maps_core_fields() -> None:
    transform = MetronApiTransform()
    result = dict(transform.to_comicbox(_sample_issue_dict()))
    cb = result["comicbox"]
    # Core scalar fields
    assert cb["page_count"] == 24
    assert cb["summary"] == "Some description."
    assert cb["collection_title"] == "Foo Comics #5"
    # Nested dicts
    assert cb["issue"]["name"] == "5"
    assert cb["series"]["name"] == "Foo Comics"
    assert cb["publisher"]["name"] == "Quality Comics"
    # Dates
    assert "cover_date" in cb["date"]
    assert "store_date" in cb["date"]
    # Cover image
    assert "cover_image" in cb


def test_to_comicbox_handles_missing_optional_fields() -> None:
    transform = MetronApiTransform()
    minimal = {
        "metron_api": {
            "id": 1,
            "number": "1",
            "cover_date": "2025-01-01",
            "modified": "2025-01-01T00:00:00Z",
            "publisher": {"id": 1, "name": "Pub"},
            "series": {"id": 1, "name": "S", "year_began": 2025, "volume": 1},
        }
    }
    result = dict(transform.to_comicbox(minimal))
    cb = result["comicbox"]
    assert cb["issue"]["name"] == "1"
    assert cb["series"]["name"] == "S"
    # Missing fields don't crash; they're just absent.
    assert "summary" not in cb or not cb.get("summary")
