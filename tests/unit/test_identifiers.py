"""Unit tests for the cross-cutting comicbox.identifiers package."""

from __future__ import annotations

from dataclasses import fields

from comicbox.box import Comicbox
from comicbox.enums.comicbox import IdSources
from comicbox.enums.maps.identifiers import get_id_source_by_alias
from comicbox.formats import MetadataFormats
from comicbox.formats.base.transforms.identifiers import (
    identifier_from_url,
)
from comicbox.identifiers import ID_TYPE_NAMES
from comicbox.identifiers.identifiers import (
    IDENTIFIER_PARTS_MAP,
    IdentifierTypes,
    create_identifier,
    get_id_source_from_url,
    get_identifier_url,
    normalize_key,
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
  urls:
    - https://metron.cloud/issue/batman-2016-0/
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
    """An identifier holds only the key; its url is derived on demand."""
    identifier = create_identifier(
        "metron", "super-series", positional_id_type="series"
    )
    assert identifier == {"key": "super-series"}
    url = get_identifier_url("metron", "series", identifier["key"])
    assert url == "https://metron.cloud/series/super-series"
    # The generated url parses back to the same source.
    assert get_id_source_from_url(url) == IdSources.METRON.value


def test_create_identifier_records_a_type_the_string_named() -> None:
    """
    A type the identifier string states is kept; one implied by place is not.

    The stored type is what decides which url the key builds, so it only
    matters when it differs from the type of the field the id sits in.
    """
    assert create_identifier("metron", "5678", id_type="series") == {
        "key": "5678",
        "id_type": "series",
    }
    assert create_identifier("metron", "series:5678") == {
        "key": "5678",
        "id_type": "series",
    }
    assert create_identifier("metron", "series:5678", positional_id_type="series") == {
        "key": "5678"
    }


def test_create_identifier_comicvine_normalizes_long_key() -> None:
    """A full comicvine '4000-12345' code is normalized to the bare key."""
    assert create_identifier("comicvine", "4000-12345") == {"key": "12345"}


def test_create_identifier_comicvine_bare_key_round_trips() -> None:
    """A bare comicvine key produces the same identifier as the long form."""
    assert create_identifier("comicvine", "12345") == create_identifier(
        "comicvine", "4000-12345"
    )


def test_create_identifier_empty_source_uses_default() -> None:
    """An empty id source falls back to the comicvine default."""
    assert create_identifier("", "999") == {"key": "999"}
    assert (
        get_identifier_url("comicvine", "issue", "999")
        == "https://comicvine.gamespot.com/c/4000-999/"
    )


def test_create_identifier_unknown_source_keeps_key_without_url() -> None:
    """An unrecognized source still records the key but cannot build a url."""
    assert create_identifier("notasource", "abc") == {"key": "abc"}


def test_create_identifier_stores_no_url() -> None:
    """Identifiers never carry a url; web links live in the urls list."""
    assert create_identifier("metron", "k") == {"key": "k"}


###############
# normalize_key
###############


def test_normalize_key_type_prefix_overrides_type() -> None:
    """A 'type:key' key yields the prefixed type and the bare key."""
    assert normalize_key("leagueofcomicgeeks", "issue", "series:178012") == (
        "series",
        "178012",
    )


def test_normalize_key_urn_prefix_unwrapped() -> None:
    """A full urn pasted as a key unwraps to its type and key."""
    assert normalize_key("comicvine", "", "urn:comicvine:issue:145269") == (
        "issue",
        "145269",
    )


def test_normalize_key_same_source_prefix_and_long_code() -> None:
    """A redundant same-source prefix strips; comicvine long codes normalize."""
    assert normalize_key("comicvine", "issue", "comicvine:4050-160294") == (
        "series",
        "160294",
    )


def test_normalize_key_foreign_source_prefix_untouched() -> None:
    """A prefix naming a different source is preserved verbatim."""
    assert normalize_key("metron", "issue", "comicvine:issue:1") == (
        "issue",
        "comicvine:issue:1",
    )


def test_normalize_key_bare_key_unchanged() -> None:
    """A clean key passes through with the caller's type."""
    assert normalize_key("metron", "series", "5678") == ("series", "5678")


def test_id_type_names_match_identifier_types_fields() -> None:
    """Drift guard: ID_TYPE_NAMES mirrors IdentifierTypes' public fields."""
    public_fields = {
        f.name for f in fields(IdentifierTypes) if not f.name.startswith("_")
    }
    assert frozenset(ID_TYPE_NAMES) == public_fields


def test_create_identifier_type_prefixed_keys_bug_report_sources() -> None:
    """'series:'-prefixed keys still build series urls for the four reported dbs."""
    cases = (
        (
            "leagueofcomicgeeks",
            "series:178012",
            "178012",
            "https://leagueofcomicgeeks.com/comics/series/178012/s",
        ),
        (
            "comicvine",
            "series:160294",
            "160294",
            "https://comicvine.gamespot.com/c/4050-160294/",
        ),
        ("metron", "series:5678", "5678", "https://metron.cloud/series/5678"),
        ("grandcomicsdatabase", "series:999", "999", "https://comics.org/series/999/"),
    )
    for id_source, raw_key, key, url in cases:
        # The prefix overrode the issue type the key was written at, so the
        # identifier records the type that decides its url.
        identifier = create_identifier(id_source, raw_key)
        assert identifier == {"key": key, "id_type": "series"}
        assert get_identifier_url(id_source, identifier["id_type"], key) == url


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


def test_get_identifier_url_colon_in_key_is_empty() -> None:
    """A key with an unrecognized prefix yields no url rather than a bad one."""
    assert get_identifier_url("metron", "issue", "comicvine:issue:1") == ""


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


def test_parse_identifier_other_str_source_type_key() -> None:
    """A 'source:type:key' string parses all three parts without truncation."""
    assert parse_identifier_other_str("leagueofcomicgeeks:series:178012") == (
        IdSources.LCG,
        "series",
        "178012",
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


def test_to_urn_string_round_trip_omits_the_default_type() -> None:
    """An issue urn carries no type segment and parses back as an issue."""
    urn = to_urn_string("comicvine", "issue", "45722")
    assert urn == "urn:comicvine:45722"
    assert parse_urn_identifier(urn) == (IdSources.COMICVINE, "issue", "45722")
    # An unstated type means the default type too.
    assert to_urn_string("comicvine", "", "45722") == urn


def test_to_urn_string_writes_an_overriding_type() -> None:
    """A type that isn't the default is named, so it survives the round trip."""
    urn = to_urn_string("metron", "series", "178012")
    assert urn == "urn:metron:series:178012"
    assert parse_urn_identifier(urn) == (IdSources.METRON, "series", "178012")


def test_to_urn_string_refuses_parts_that_cannot_make_a_urn() -> None:
    """
    Unusable parts yield no urn instead of raising.

    The notes stamp composes urns from hand written identifier sources, so a
    source that is not a legal urn namespace must not abort the whole read.
    """
    assert to_urn_string("weird.dotted", "issue", "1") == ""
    assert to_urn_string("my_db", "issue", "abc") == ""
    assert to_urn_string("x", "issue", "1") == ""
    assert to_urn_string("metron", "issue", "abc def") == ""
    assert to_urn_string("metron", "issue", "") == ""
    # A type comicbox doesn't know would read back as an issue id.
    assert to_urn_string("metron", "map", "1") == ""


def test_parse_urn_identifier_scheme_and_type_are_case_insensitive() -> None:
    """RFC 8141 makes the scheme case insensitive, and comicbox the type."""
    expected = (IdSources.COMICVINE, "issue", "145269")
    assert parse_urn_identifier("URN:comicvine:145269") == expected
    assert parse_urn_identifier("urn:Comicvine:Issue:145269") == expected


def test_parse_urn_identifier_rejects_a_near_urn() -> None:
    """A string that merely starts with urn is not a urn."""
    assert parse_urn_identifier("urnfoo:bar:baz") == (None, "", "")


def test_parse_urn_identifier_keeps_every_segment_of_the_key() -> None:
    """A key with colons in it stays whole instead of losing its head."""
    assert parse_urn_identifier("urn:metron:series:a:b") == (
        IdSources.METRON,
        "series",
        "a:b",
    )


def test_parse_urn_identifier_unknown_type_is_part_of_the_key() -> None:
    """An unrecognized first segment is key data, not a type to discard."""
    assert parse_urn_identifier("urn:comicvine:notatype:145269") == (
        IdSources.COMICVINE,
        "issue",
        "notatype:145269",
    )


def test_parse_urn_identifier_decodes_percent_encoded_keys() -> None:
    """Keys another tagger percent encoded still arrive decoded."""
    assert parse_urn_identifier("urn:metron:100%25") == (
        IdSources.METRON,
        "issue",
        "100%",
    )


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


###################
# identifier_from_url
###################


def test_identifier_from_url_recognized_source() -> None:
    """A url from a known database yields that database's id."""
    id_source, identifier = identifier_from_url(
        "https://comicvine.gamespot.com/c/4000-145269/"
    )
    assert id_source == "comicvine"
    assert identifier == {"key": "145269"}


def test_identifier_from_url_unknown_source() -> None:
    """A url from an unknown site yields nothing to invent an id from."""
    assert identifier_from_url("https://example.com/some/comic") == ("", {})


def test_identifier_from_url_empty() -> None:
    """An empty url yields nothing."""
    assert identifier_from_url("") == ("", {})


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
