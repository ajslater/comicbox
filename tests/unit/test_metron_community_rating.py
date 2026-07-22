"""MetronInfo CommunityRating transform guard tests."""

from decimal import Decimal

from comicbox.formats.metron_info.transform import MetronInfoTransform


def _from_cb(community_rating: dict) -> dict:
    transform = MetronInfoTransform()
    data = {"comicbox": {"community_rating": community_rating}}
    return dict(transform.from_comicbox(data)).get("MetronInfo", {})


def test_community_rating_from_cb() -> None:
    """Average and count map to the nested CommunityRating tag."""
    metron = _from_cb({"average_rating": Decimal("4.5"), "rating_count": 25})
    assert metron["CommunityRating"] == {
        "AverageRating": Decimal("4.5"),
        "RatingCount": 25,
    }


def test_community_rating_from_cb_average_only() -> None:
    """A lone average omits RatingCount."""
    metron = _from_cb({"average_rating": Decimal("3.0")})
    assert metron["CommunityRating"] == {"AverageRating": Decimal("3.0")}


def test_community_rating_from_cb_count_only_omits_tag() -> None:
    """The XSD requires AverageRating, so a lone count emits no tag at all."""
    metron = _from_cb({"rating_count": 25})
    assert "CommunityRating" not in metron
