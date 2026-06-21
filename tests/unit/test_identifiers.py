"""Unit tests for the cross-cutting comicbox.identifiers package."""

from __future__ import annotations

from comicbox.box import Comicbox
from comicbox.enums.comicbox import IdSources
from comicbox.enums.maps.identifiers import get_id_source_by_alias
from comicbox.formats import MetadataFormats
from comicbox.formats.base.transforms.identifiers import (
    merge_url_and_explicit_identifiers,
)
from comicbox.identifiers.identifiers import (
    IDENTIFIER_PARTS_MAP,
    create_identifier,
    get_id_source_from_url,
    get_identifier_url,
)
from comicbox.identifiers.other import parse_identifier_other_str
from comicbox.identifiers.urns import (
    parse_string_identifier,
    parse_urn_identifier,
    to_urn_string,
)

# A Metron-tagged issue carrying both the numeric id and the slug web url —
# the shape that exposed the url-clobbers-key bug.
_METRON_SOURCE_YAML = """
comicbox:
  issue: "0"
  identifiers:
    metron:
      key: "123495"
      url: https://metron.cloud/issue/batman-2016-0/
"""


def _round_trip_metron_key(fmt: MetadataFormats) -> str | None:
    """Render the sample to ``fmt`` then read it back; return identifiers.metron.key."""
    with Comicbox() as cb:
        cb.add_metadata(_METRON_SOURCE_YAML, MetadataFormats.COMICBOX_YAML)
        rendered = cb.to_string(fmt)
    with Comicbox() as cb2:
        cb2.add_metadata(rendered, fmt)
        comicbox_md = cb2.to_dict().get("comicbox", {})
    return comicbox_md.get("identifiers", {}).get("metron", {}).get("key")

###################
# create_identifier
###################


def test_create_identifier_round_trip_metron() -> None:
    """A metron series identifier gets both a key and a metron.cloud url."""
    identifier = create_identifier("metron", "super-series", id_type="series")
    assert identifier == {
        "key": "super-series",
        "url": "https://metron.cloud/series/super-series",
    }
    # The generated url parses back to the same source.
    assert get_id_source_from_url(identifier["url"]) == IdSources.METRON.value


def test_create_identifier_comicvine_normalizes_long_key() -> None:
    """A full comicvine '4000-12345' code is normalized to the bare key."""
    identifier = create_identifier("comicvine", "4000-12345")
    assert identifier == {
        "key": "12345",
        "url": "https://comicvine.gamespot.com/c/4000-12345/",
    }


def test_create_identifier_comicvine_bare_key_round_trips() -> None:
    """A bare comicvine key produces the same identifier as the long form."""
    assert create_identifier("comicvine", "12345") == create_identifier(
        "comicvine", "4000-12345"
    )


def test_create_identifier_empty_source_uses_default() -> None:
    """An empty id source falls back to the comicvine default."""
    identifier = create_identifier("", "999")
    assert identifier == {
        "key": "999",
        "url": "https://comicvine.gamespot.com/c/4000-999/",
    }


def test_create_identifier_unknown_source_keeps_key_without_url() -> None:
    """An unrecognized source still records the key but cannot build a url."""
    assert create_identifier("notasource", "abc") == {"key": "abc"}


def test_create_identifier_explicit_url_wins() -> None:
    """An explicitly passed url is preserved instead of being generated."""
    identifier = create_identifier("metron", "k", url="https://example.com/x")
    assert identifier == {"key": "k", "url": "https://example.com/x"}


#####################
# get_identifier_url
#####################


def test_get_identifier_url_metron_and_comicvine() -> None:
    """The major sources produce their documented url shapes."""
    assert (
        get_identifier_url("metron", "issue", "flash-2021-1")
        == "https://metron.cloud/issue/flash-2021-1"
    )
    assert (
        get_identifier_url("comicvine", "issue", "12345")
        == "https://comicvine.gamespot.com/c/4000-12345/"
    )


def test_get_identifier_url_unknown_source_or_type_is_empty() -> None:
    """Unknown sources and unmapped id types yield an empty url string."""
    assert get_identifier_url("unknownsource", "issue", "1") == ""
    assert get_identifier_url("comicvine", "bogus_type", "12345") == ""


def test_url_path_parses_back_to_type_and_key() -> None:
    """IdentifierParts.parse_url_path inverts unparse_url for comicvine."""
    parts = IDENTIFIER_PARTS_MAP[IdSources.COMICVINE]
    url = parts.unparse_url("issue", "12345")
    assert parts.parse_url_path(url) == ("issue", "12345")


def test_metron_url_path_strips_trailing_slash() -> None:
    """
    A trailing slash in a metron url is not captured into the id key.

    Metron issue urls carry a trailing slash (…/issue/123495/). The id key
    regex must stop at the path separator so the key stays a bare id and not
    '123495/', which would fail an int() parse on the stored-id fast path.
    """
    parts = IDENTIFIER_PARTS_MAP[IdSources.METRON]
    assert parts.parse_url_path("https://metron.cloud/issue/123495/") == (
        "issue",
        "123495",
    )
    assert parts.parse_url_path("https://metron.cloud/issue/batman-2016-0/") == (
        "issue",
        "batman-2016-0",
    )


def test_get_id_source_from_url_unknown_domain_returns_netloc() -> None:
    """An unrecognized domain falls back to returning the netloc itself."""
    assert get_id_source_from_url("https://example.com/foo") == "example.com"


######################
# parse_urn_identifier
######################


def test_parse_urn_identifier_with_type() -> None:
    """A three-part urn yields source, type and key."""
    assert parse_urn_identifier("urn:metron:issue:2002") == (
        IdSources.METRON,
        "issue",
        "2002",
    )


def test_parse_urn_identifier_comicvine_long_key_not_normalized() -> None:
    """
    A two-part comicvine urn defaults the type and keeps the raw key.

    The urn layer does no comicvine long-key normalization; that happens
    later in create_identifier.
    """
    assert parse_urn_identifier("urn:comicvine:4000-45722") == (
        IdSources.COMICVINE,
        "issue",
        "4000-45722",
    )


def test_parse_urn_identifier_garbage() -> None:
    """Empty and malformed strings yield the empty no-source tuple."""
    assert parse_urn_identifier("") == (None, "", "")
    assert parse_urn_identifier("not a urn") == (None, "", "")


def test_parse_urn_identifier_unknown_nid_yields_no_source() -> None:
    """A valid urn with an unknown nid parses the key but no source."""
    assert parse_urn_identifier("urn:unknownnid:123") == (None, "issue", "123")


############################
# parse_identifier_other_str
############################


def test_parse_identifier_other_str_cvdb_alias_case_insensitive() -> None:
    """The cvdb alias prefix is matched case-insensitively."""
    expected = (IdSources.COMICVINE, "issue", "12345")
    assert parse_identifier_other_str("cvdb12345") == expected
    assert parse_identifier_other_str("CVDB12345") == expected


def test_parse_identifier_other_str_source_prefix() -> None:
    """A 'source:key' string parses into source and key."""
    assert parse_identifier_other_str("metron:abc-123") == (
        IdSources.METRON,
        "issue",
        "abc-123",
    )


def test_parse_identifier_other_str_comicvine_long_code() -> None:
    """A bare comicvine long code is recognized and split."""
    assert parse_identifier_other_str("4000-45722") == (
        IdSources.COMICVINE,
        "issue",
        "45722",
    )


def test_parse_identifier_other_str_garbage_falls_back_to_key() -> None:
    """Unparseable input becomes the key itself with no source or type."""
    assert parse_identifier_other_str("garbage with spaces") == (
        None,
        "",
        "garbage with spaces",
    )
    assert parse_identifier_other_str("") == (None, "", "")


##########################################
# parse_string_identifier & to_urn_string
##########################################


def test_parse_string_identifier_prefers_urn_then_other() -> None:
    """Urn strings and other-style strings both parse via the one entrypoint."""
    assert parse_string_identifier("urn:metron:issue:2002") == (
        IdSources.METRON,
        "issue",
        "2002",
    )
    assert parse_string_identifier("cvdb12345") == (
        IdSources.COMICVINE,
        "issue",
        "12345",
    )


def test_parse_string_identifier_uses_default_source_for_bare_key() -> None:
    """A bare key gets the caller's default source and the default type."""
    assert parse_string_identifier("justakey", IdSources.METRON) == (
        IdSources.METRON,
        "issue",
        "justakey",
    )


def test_to_urn_string_round_trip_and_dotted_source_rejected() -> None:
    """to_urn_string composes a urn that parses back; dotted sources abort."""
    urn = to_urn_string("comicvine", "issue", "45722")
    assert urn == "urn:comicvine:issue:45722"
    assert parse_urn_identifier(urn) == (IdSources.COMICVINE, "issue", "45722")
    # Domain-like source strings cannot be urn nids.
    assert to_urn_string("weird.dotted", "issue", "1") == ""


########################
# get_id_source_by_alias
########################


def test_get_id_source_by_alias_case_insensitive() -> None:
    """Enum values, display names, and domains all resolve case-insensitively."""
    assert get_id_source_by_alias("METRON") == IdSources.METRON
    assert get_id_source_by_alias("Comic Vine") == IdSources.COMICVINE
    assert get_id_source_by_alias("metron.cloud") == IdSources.METRON


def test_get_id_source_by_alias_unknown_uses_default() -> None:
    """Unknown aliases return the passed default (comicvine when omitted)."""
    assert get_id_source_by_alias("never-heard-of-it") == IdSources.COMICVINE
    assert get_id_source_by_alias("never-heard-of-it", None) is None


####################################
# merge_url_and_explicit_identifiers
####################################


def test_merge_explicit_id_key_beats_url_slug_but_keeps_real_url() -> None:
    """An explicit numeric key wins over a url slug; the real url is kept."""
    url_identifiers = {
        "metron": {"key": "batman-2016-0", "url": "https://metron.cloud/issue/b/"}
    }
    explicit_identifiers = {
        "metron": {"key": "123495", "url": "https://metron.cloud/issue/123495"}
    }
    merged = merge_url_and_explicit_identifiers(url_identifiers, explicit_identifiers)
    assert merged == {
        "metron": {"key": "123495", "url": "https://metron.cloud/issue/b/"}
    }


def test_merge_url_only_supplies_fallback_key_and_url() -> None:
    """With no explicit id, the url-derived key and url survive as a fallback."""
    url_identifiers = {
        "metron": {"key": "batman-2016-0", "url": "https://metron.cloud/issue/b/"}
    }
    assert merge_url_and_explicit_identifiers(url_identifiers) == url_identifiers


def test_merge_explicit_only_passes_through() -> None:
    """With no url identifiers the explicit identifiers pass through intact."""
    explicit = {"metron": {"key": "123495", "url": "https://metron.cloud/issue/123495"}}
    assert merge_url_and_explicit_identifiers({}, explicit) == explicit


#####################################################
# write -> read round trip preserves the numeric key
#####################################################


def test_metron_id_survives_comic_info_round_trip() -> None:
    """
    A Metron issue id written to ComicInfo reads back as the numeric key.

    Regression guard: a <Web> url slug used to clobber the authoritative GTIN
    id on read-back, breaking comicbox's stored-id fast path so already-tagged
    comics fell through to a full online search.
    """
    assert _round_trip_metron_key(MetadataFormats.COMIC_INFO) == "123495"


def test_metron_id_survives_metron_info_round_trip() -> None:
    """A Metron issue id written to MetronInfo reads back as the numeric key."""
    assert _round_trip_metron_key(MetadataFormats.METRON_INFO) == "123495"
