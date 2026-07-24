"""MetronApiTransform field-mapping tests."""

from __future__ import annotations

from decimal import Decimal

from comicbox.formats.metron_api.transform import MetronApiTransform


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
            "average_rating": "4.5",
            "rating_count": 25,
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
    assert {k: cb[k] for k in ("page_count", "summary", "collection_title")} == {
        "page_count": 24,
        "summary": "Some description.",
        "collection_title": "Foo Comics #5",
    }
    # Nested resource names
    assert {k: cb[k]["name"] for k in ("issue", "series", "publisher")} == {
        "issue": "5",
        "series": "Foo Comics",
        "publisher": "Quality Comics",
    }
    assert cb["community_rating"] == {
        "average_rating": Decimal("4.5"),
        "rating_count": 25,
    }
    # Dates and cover image are present
    assert {"cover_date", "store_date"} <= cb["date"].keys()
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
            # Mokkari reports unrated issues as a null average with a 0 count.
            "average_rating": None,
            "rating_count": 0,
        }
    }
    result = dict(transform.to_comicbox(minimal))
    cb = result["comicbox"]
    assert cb["issue"]["name"] == "1"
    assert cb["series"]["name"] == "S"
    # Missing fields don't crash; they're just absent.
    assert "summary" not in cb or not cb.get("summary")
    # Unrated must not emit a block: the 0 count would clamp up to the
    # native field minimum of 1.
    assert "community_rating" not in cb


def test_prices_currency_mapped_to_country_code() -> None:
    """USD → US so the country-keyed comicbox price dict accepts it."""
    transform = MetronApiTransform()
    payload = _sample_issue_dict()
    payload["metron_api"]["price"] = "4.99"
    payload["metron_api"]["price_currency"] = "USD"
    result = dict(transform.to_comicbox(payload))
    assert result["comicbox"]["prices"] == {"US": Decimal("4.99")}


def test_prices_unknown_currency_falls_back_to_empty_key() -> None:
    """Unrecognized currency code yields an empty country key, not a warning."""
    transform = MetronApiTransform()
    payload = _sample_issue_dict()
    payload["metron_api"]["price"] = "4.99"
    payload["metron_api"]["price_currency"] = "XYZ"
    result = dict(transform.to_comicbox(payload))
    assert result["comicbox"]["prices"] == {"": Decimal("4.99")}


def test_prices_missing_returns_empty_dict() -> None:
    """No price means no prices entry."""
    transform = MetronApiTransform()
    result = dict(transform.to_comicbox(_sample_issue_dict()))
    assert result["comicbox"].get("prices", {}) == {}
