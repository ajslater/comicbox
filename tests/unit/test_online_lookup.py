"""ComicboxOnlineLookup mixin tests (M2: --id path)."""

from __future__ import annotations

from argparse import Namespace
from collections.abc import Mapping
from io import BytesIO
from types import MappingProxyType
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from PIL import Image

from comicbox.box import Comicbox
from comicbox.box.online_lookup import ComicboxOnlineLookup
from comicbox.formats import MetadataFormats
from comicbox.formats.sources import MetadataSources

if TYPE_CHECKING:
    from comicbox.formats.base.online.profile import Candidate

_SAMPLE_ISSUE = {
    "id": 42,
    "number": "5",
    "cover_date": "2020-04-01",
    "modified": "2020-04-02T12:00:00Z",
    "page_count": 24,
    "desc": "Sample description",
    "publisher": {"id": 1, "name": "Quality Comics"},
    "series": {
        "id": 100,
        "name": "Foo Comics",
        "year_began": 2018,
        "volume": 1,
    },
}


class _FakeMetronSource:
    """Mock OnlineSource that records get() calls."""

    name = "metron"
    metadata_source = MetadataSources.METRON_API
    metadata_format = MetadataFormats.METRON_API

    def __init__(self, credentials, settings, *, payload=None) -> None:
        self._credentials = credentials
        self._settings = settings
        self.get_calls: list[int] = []
        self.search_calls: list = []
        self._payload = payload or _SAMPLE_ISSUE

    def is_configured(self) -> bool:
        return bool(self._credentials.user and self._credentials.password)

    def get(self, issue_id: int) -> dict:
        self.get_calls.append(issue_id)
        return dict(self._payload)

    def search(self, profile) -> list[Candidate]:
        self.search_calls.append(profile)
        return []


@pytest.fixture
def patched_metron(monkeypatch: pytest.MonkeyPatch) -> list[_FakeMetronSource]:
    """Replace the Metron factory with a fake; expose every instance."""
    instances: list[_FakeMetronSource] = []

    def factory(creds, settings):
        src = _FakeMetronSource(creds, settings)
        instances.append(src)
        return src

    factories = MappingProxyType({"metron": factory})
    monkeypatch.setattr(ComicboxOnlineLookup, "_ONLINE_SOURCE_FACTORIES", factories)
    return instances


def _build_cb(**comicbox_kwargs) -> Comicbox:
    """Build a Comicbox with an inline config; no archive path required."""
    return Comicbox(config=Namespace(comicbox=Namespace(**comicbox_kwargs)))


def test_lookup_disabled_when_online_off(patched_metron) -> None:
    cb = _build_cb(metadata={})
    cb.get_merged_metadata()
    assert patched_metron == []


def test_explicit_id_triggers_get(patched_metron) -> None:
    args = Namespace(
        comicbox=Namespace(
            online_sources=["metron"],
            explicit_ids=["metron:42"],
            auth=["metron:user=u", "metron:pass=p"],
        )
    )
    cb = Comicbox(config=args)
    cb.get_merged_metadata()
    assert len(patched_metron) == 1
    assert patched_metron[0].get_calls == [42]


def test_explicit_id_payload_appears_as_metron_api_source(
    patched_metron,
) -> None:
    args = Namespace(
        comicbox=Namespace(
            online_sources=["metron"],
            explicit_ids=["metron:42"],
            auth=["metron:user=u", "metron:pass=p"],
        )
    )
    cb = Comicbox(config=args)
    cb.get_merged_metadata()
    sd = cb.get_source_metadata(MetadataSources.METRON_API)
    assert sd is not None
    assert len(sd) == 1
    # The payload was wrapped under the schema's ROOT_TAG.
    payload = sd[0].data
    assert isinstance(payload, Mapping)
    assert "metron_api" in payload


def test_unconfigured_source_skipped(patched_metron) -> None:
    args = Namespace(
        comicbox=Namespace(
            online_sources=["metron"],
            explicit_ids=["metron:42"],
            # Explicitly set blank creds so the test isolates from
            # ~/.config/comicbox/config.yaml or env vars on the developer's
            # machine — otherwise is_configured() returns True and the
            # "skip unconfigured" branch we're testing never fires.
            auth=[],  # explicitly unconfigured metron,
        )
    )
    cb = Comicbox(config=args)
    cb.get_merged_metadata()
    # The factory was called but the resulting source's is_configured() is False
    # so no get() happens.
    assert all(src.get_calls == [] for src in patched_metron)


def test_lookup_idempotent(patched_metron) -> None:
    args = Namespace(
        comicbox=Namespace(
            online_sources=["metron"],
            explicit_ids=["metron:42"],
            auth=["metron:user=u", "metron:pass=p"],
        )
    )
    cb = Comicbox(config=args)
    cb.run_online_lookup()
    cb.run_online_lookup()  # second call should not refetch
    assert patched_metron[0].get_calls == [42]


def test_filter_excludes_unselected_source(patched_metron) -> None:
    args = Namespace(
        comicbox=Namespace(
            online_sources=["comicvine"],  # filter excludes metron
            auth=["metron:user=u", "metron:pass=p"],
        )
    )
    cb = Comicbox(config=args)
    cb.run_online_lookup()
    # No factory invocations because metron isn't in selected_sources
    # (and no `--id metron:...` to force-include it).
    assert patched_metron == []


def test_explicit_id_for_unconfigured_source_warns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--id comicvine:42` without CV creds should warn loudly."""

    class _UnconfiguredCV:
        name = "comicvine"
        metadata_source = MetadataSources.COMICVINE_API
        metadata_format = MetadataFormats.COMICVINE_API

        def __init__(self, credentials, settings) -> None:
            self._credentials = credentials

        def is_configured(self) -> bool:
            return False  # No key configured.

        def get(self, issue_id: int) -> dict:
            return {}

        def search(self, profile) -> list[Candidate]:
            return []

    monkeypatch.setattr(
        ComicboxOnlineLookup,
        "_ONLINE_SOURCE_FACTORIES",
        MappingProxyType({"comicvine": _UnconfiguredCV}),
    )

    warnings: list[str] = []
    monkeypatch.setattr(
        "comicbox.box.online_lookup.logger.warning",
        warnings.append,
    )

    args = Namespace(
        comicbox=Namespace(
            explicit_ids=["comicvine:42"],
            # No comicvine creds.
        )
    )
    cb = Comicbox(config=args)
    cb.run_online_lookup()
    assert any("--id comicvine:42" in m for m in warnings), (
        f"expected warning about --id comicvine:42; got {warnings}"
    )


def test_online_all_with_no_configured_sources_warns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--online all` with no creds for any source should warn loudly."""

    class _UnconfiguredSource:
        name = "metron"
        metadata_source = MetadataSources.METRON_API
        metadata_format = MetadataFormats.METRON_API

        def __init__(self, credentials, settings) -> None:
            self._credentials = credentials

        def is_configured(self) -> bool:
            return False

        def get(self, issue_id: int) -> dict:
            return {}

        def search(self, profile) -> list[Candidate]:
            return []

    monkeypatch.setattr(
        ComicboxOnlineLookup,
        "_ONLINE_SOURCE_FACTORIES",
        MappingProxyType({"metron": _UnconfiguredSource}),
    )

    warnings: list[str] = []
    monkeypatch.setattr(
        "comicbox.box.online_lookup.logger.warning",
        warnings.append,
    )

    args = Namespace(
        comicbox=Namespace(
            online_sources=["all"],
            auth=[],
        )
    )
    cb = Comicbox(config=args)
    cb.run_online_lookup()
    assert any("no sources are configured" in m for m in warnings), (
        f"expected 'no sources are configured' warning; got {warnings}"
    )


# ----------------------------------------- cross-source cv_id disagreement


def test_detect_cv_id_disagreement_returns_pair_when_different() -> None:
    from comicbox.box.online_lookup import _detect_cv_id_disagreement

    metron = {"comicbox": {"identifiers": {"comicvine": {"key": "999"}}}}
    cv = {"comicbox": {"identifiers": {"comicvine": {"key": "1234"}}}}
    assert _detect_cv_id_disagreement(metron, cv) == ("999", "1234")


def test_detect_cv_id_disagreement_returns_none_when_matching() -> None:
    from comicbox.box.online_lookup import _detect_cv_id_disagreement

    metron = {"comicbox": {"identifiers": {"comicvine": {"key": "999"}}}}
    cv = {"comicbox": {"identifiers": {"comicvine": {"key": "999"}}}}
    assert _detect_cv_id_disagreement(metron, cv) is None


def test_detect_cv_id_disagreement_returns_none_when_one_missing() -> None:
    from comicbox.box.online_lookup import _detect_cv_id_disagreement

    metron = {"comicbox": {"identifiers": {"comicvine": {"key": "999"}}}}
    # CV missing → cannot compare.
    assert _detect_cv_id_disagreement(metron, None) is None
    # Metron missing → cannot compare.
    assert _detect_cv_id_disagreement(None, metron) is None
    # CV has no comicvine identifier (e.g. CV source didn't run) → skip.
    cv_no_key: dict = {"comicbox": {"identifiers": {}}}
    assert _detect_cv_id_disagreement(metron, cv_no_key) is None


def test_detect_cv_id_disagreement_coerces_int_keys() -> None:
    """Identifiers can come through as int or str; comparison normalizes."""
    from comicbox.box.online_lookup import _detect_cv_id_disagreement

    metron = {"comicbox": {"identifiers": {"comicvine": {"key": 999}}}}
    cv = {"comicbox": {"identifiers": {"comicvine": {"key": "999"}}}}
    assert _detect_cv_id_disagreement(metron, cv) is None


# Integration: cross-source warning fires when both sources contribute
# disagreeing comicvine identifiers. We patch both factories and assert
# the warning logger received the expected message.


_METRON_PAYLOAD_CV_ID_999 = {
    "id": 42,
    "number": "5",
    "cover_date": "2020-04-01",
    "modified": "2020-04-02T12:00:00Z",
    "page_count": 24,
    "publisher": {"id": 1, "name": "Quality Comics"},
    "series": {
        "id": 100,
        "name": "Foo Comics",
        "year_began": 2018,
        "volume": 1,
    },
    "cv_id": 999,  # Metron's stored cross-reference to ComicVine
}


_CV_PAYLOAD_ID_1234 = {
    "id": 1234,
    "number": "5",
    "cover_date": "2020-04-01",
    "date_last_updated": "2020-04-02T12:00:00Z",
    "image": {"medium_url": "http://t.example.com/m.jpg"},
    "volume": {"id": 50, "name": "Foo Comics"},
}


def _make_dual_factories(metron_payload: dict, cv_payload: dict) -> dict:
    """Two source factories returning fixed payloads — for cross-source tests."""

    class _FakeCV:
        name = "comicvine"
        metadata_source = MetadataSources.COMICVINE_API
        metadata_format = MetadataFormats.COMICVINE_API

        def __init__(self, credentials, settings) -> None:
            self._credentials = credentials

        def is_configured(self) -> bool:
            return bool(self._credentials.key)

        def get(self, issue_id: int) -> dict:
            return dict(cv_payload)

        def search(self, profile) -> list[Candidate]:
            return []

    def metron_factory(creds, settings):
        return _FakeMetronSource(creds, settings, payload=metron_payload)

    return {"metron": metron_factory, "comicvine": _FakeCV}


def test_cross_source_warning_fires_on_cv_id_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Metron's cv_id=999 vs CV's id=1234 → warning logged."""
    factories = _make_dual_factories(_METRON_PAYLOAD_CV_ID_999, _CV_PAYLOAD_ID_1234)
    monkeypatch.setattr(
        ComicboxOnlineLookup,
        "_ONLINE_SOURCE_FACTORIES",
        MappingProxyType(factories),
    )

    warnings: list[str] = []
    monkeypatch.setattr(
        "comicbox.box.online_lookup.logger.warning",
        warnings.append,
    )

    args = Namespace(
        comicbox=Namespace(
            explicit_ids=["metron:42", "comicvine:1234"],
            auth=["metron:user=u", "metron:pass=p", "comicvine:key=k"],
        )
    )
    cb = Comicbox(config=args)
    cb.run_online_lookup()

    cross_warnings = [m for m in warnings if "cross-source" in m]
    assert cross_warnings, f"expected cross-source warning; got {warnings}"
    assert "999" in cross_warnings[0]
    assert "1234" in cross_warnings[0]


def test_cross_source_no_warning_when_cv_ids_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Metron cv_id == CV id → no warning."""
    metron_payload_match = dict(_METRON_PAYLOAD_CV_ID_999, cv_id=1234)
    factories = _make_dual_factories(metron_payload_match, _CV_PAYLOAD_ID_1234)
    monkeypatch.setattr(
        ComicboxOnlineLookup,
        "_ONLINE_SOURCE_FACTORIES",
        MappingProxyType(factories),
    )

    warnings: list[str] = []
    monkeypatch.setattr(
        "comicbox.box.online_lookup.logger.warning",
        warnings.append,
    )

    args = Namespace(
        comicbox=Namespace(
            explicit_ids=["metron:42", "comicvine:1234"],
            auth=["metron:user=u", "metron:pass=p", "comicvine:key=k"],
        )
    )
    cb = Comicbox(config=args)
    cb.run_online_lookup()

    cross_warnings = [m for m in warnings if "cross-source" in m]
    assert cross_warnings == [], (
        f"unexpected cross-source warning when ids agree: {cross_warnings}"
    )


# ----------------------------------------- _resolve_volume year-as-volume guard


def test_resolve_volume_extracts_real_ordinal() -> None:
    from comicbox.formats.base.online.profile import _resolve_volume

    assert _resolve_volume({"comicbox": {"volume": {"number": 2}}}) == 2
    assert _resolve_volume({"comicbox": {"volume": {"number": "5"}}}) == 5


def test_resolve_volume_rejects_year_shape() -> None:
    """
    ComicInfo.xml convention uses year-of-first-issue as volume.

    Metron's `series_volume` filter expects an ordinal — sending 2019
    matches no issues. We drop year-shaped values (1900-2100) so they
    don't poison the search.
    """
    from comicbox.formats.base.online.profile import _resolve_volume

    assert _resolve_volume({"comicbox": {"volume": {"number": 2019}}}) is None
    assert _resolve_volume({"comicbox": {"volume": {"number": "1986"}}}) is None
    assert _resolve_volume({"comicbox": {"volume": {"number": 2100}}}) is None
    assert _resolve_volume({"comicbox": {"volume": {"number": 1900}}}) is None


def test_resolve_volume_keeps_pre_1900_values() -> None:
    """Pre-1900 volume numbers can't be year-shaped; keep them."""
    from comicbox.formats.base.online.profile import _resolve_volume

    assert _resolve_volume({"comicbox": {"volume": {"number": 1899}}}) == 1899
    assert _resolve_volume({"comicbox": {"volume": {"number": 50}}}) == 50


def test_resolve_volume_keeps_post_2100_values() -> None:
    """Post-2100 volume numbers can't be year-shaped (sci-fi aside); keep them."""
    from comicbox.formats.base.online.profile import _resolve_volume

    assert _resolve_volume({"comicbox": {"volume": {"number": 2101}}}) == 2101


def test_resolve_volume_handles_missing_or_garbage() -> None:
    from comicbox.formats.base.online.profile import _resolve_volume

    assert _resolve_volume({}) is None
    assert _resolve_volume({"comicbox": {}}) is None
    assert _resolve_volume({"comicbox": {"volume": {"number": "abc"}}}) is None


# ----------------------------------------- accumulate_profile_fields precedence


def _md(**comicbox_fields: object) -> dict:
    """Wrap fields under the comicbox root tag the profile paths expect."""
    return {"comicbox": comicbox_fields}


def test_accumulate_profile_fields_embedded_beats_filename() -> None:
    """
    Later (higher-precedence) source overwrites earlier — matches the merge.

    `_build_profile` feeds sources in `MetadataSources` order, where
    `ARCHIVE_FILENAME` precedes `ARCHIVE_FILE`. The online search must use
    the embedded series, not the filename parse, just like the merged
    metadata does. Regression for the first-wins precedence inversion.
    """
    from comicbox.formats.base.online.profile import accumulate_profile_fields

    fields: dict = {}
    # Filename parse first (earlier source) ...
    accumulate_profile_fields(fields, _md(series={"name": "Spider-Man"}))
    # ... then the embedded ComicInfo.xml (later, higher-precedence source).
    accumulate_profile_fields(fields, _md(series={"name": "The Amazing Spider-Man"}))
    assert fields["series"] == "The Amazing Spider-Man"


def test_accumulate_profile_fields_keeps_earlier_when_later_absent() -> None:
    """A later source that lacks the field leaves the filename value intact."""
    from comicbox.formats.base.online.profile import accumulate_profile_fields

    fields: dict = {}
    accumulate_profile_fields(fields, _md(series={"name": "Spider-Man"}))
    accumulate_profile_fields(fields, _md(publisher={"name": "Marvel"}))
    assert fields["series"] == "Spider-Man"
    assert fields["publisher"] == "Marvel"


# ----------------------------------------- first-wins, tag-all, stored-id, force-search


def _dual_factories_for_first_wins(
    metron_payload: dict | None = None,
) -> tuple[list[_FakeMetronSource], list, dict]:
    """Build metron + cv factories that record their instances."""
    metron_instances: list[_FakeMetronSource] = []
    cv_instances: list = []

    class _FakeCV:
        name = "comicvine"
        metadata_source = MetadataSources.COMICVINE_API
        metadata_format = MetadataFormats.COMICVINE_API

        def __init__(self, credentials, settings) -> None:
            self._credentials = credentials
            self.get_calls: list[int] = []
            self.search_calls: list = []
            cv_instances.append(self)

        def is_configured(self) -> bool:
            return bool(self._credentials.key)

        def get(self, issue_id: int) -> dict:
            self.get_calls.append(issue_id)
            return dict(_CV_PAYLOAD_ID_1234)

        def search(self, profile) -> list[Candidate]:
            self.search_calls.append(profile)
            return []

    def metron_factory(creds, settings):
        src = _FakeMetronSource(creds, settings, payload=metron_payload)
        metron_instances.append(src)
        return src

    factories = {"metron": metron_factory, "comicvine": _FakeCV}
    return metron_instances, cv_instances, factories


def test_first_wins_skips_second_source_on_metron_explicit_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Metron contributes via --id → CV is skipped under first-wins (default)."""
    metron_instances, cv_instances, factories = _dual_factories_for_first_wins()
    monkeypatch.setattr(
        ComicboxOnlineLookup,
        "_ONLINE_SOURCE_FACTORIES",
        MappingProxyType(factories),
    )
    args = Namespace(
        comicbox=Namespace(
            # Both sources active; only metron has --id.
            online_sources=["metron", "comicvine"],
            explicit_ids=["metron:42"],
            auth=["metron:user=u", "metron:pass=p", "comicvine:key=k"],
        )
    )
    cb = Comicbox(config=args)
    cb.run_online_lookup()
    assert metron_instances[0].get_calls == [42]
    # CV factory was constructed (during _build_active_online_sources) but
    # neither get() nor search() should have been called under first-wins.
    assert cv_instances
    assert cv_instances[0].get_calls == []
    assert cv_instances[0].search_calls == []


def test_sources_order_is_run_priority(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    A comicvine-first selection runs Comic Vine first; its win skips Metron.

    Before sources became ordered, the factory map's order (metron first)
    always won: Metron would have attempted its search before Comic Vine
    got a turn. With Comic Vine listed first and contributing via --id,
    first-wins must skip Metron entirely — no search call at all.
    """
    metron_instances, cv_instances, factories = _dual_factories_for_first_wins()
    monkeypatch.setattr(
        ComicboxOnlineLookup,
        "_ONLINE_SOURCE_FACTORIES",
        MappingProxyType(factories),
    )
    args = Namespace(
        comicbox=Namespace(
            online_sources=["comicvine", "metron"],
            explicit_ids=["comicvine:1234"],
            # Searchable profile so Metron WOULD search if it ran first.
            general=Namespace(
                metadata={
                    "comicbox": {"series": {"name": "Foo"}, "issue": {"name": "5"}}
                }
            ),
            auth=["metron:user=u", "metron:pass=p", "comicvine:key=k"],
        )
    )
    cb = Comicbox(config=args)
    cb.run_online_lookup()
    assert cv_instances[0].get_calls == [1234]
    assert metron_instances[0].get_calls == []
    assert metron_instances[0].search_calls == []


def test_tag_all_sources_runs_both(monkeypatch: pytest.MonkeyPatch) -> None:
    """--all-sources lets CV run even after metron contributed."""
    metron_instances, cv_instances, factories = _dual_factories_for_first_wins()
    monkeypatch.setattr(
        ComicboxOnlineLookup,
        "_ONLINE_SOURCE_FACTORIES",
        MappingProxyType(factories),
    )
    args = Namespace(
        comicbox=Namespace(
            explicit_ids=["metron:42", "comicvine:1234"],
            all_sources=True,
            auth=["metron:user=u", "metron:pass=p", "comicvine:key=k"],
        )
    )
    cb = Comicbox(config=args)
    cb.run_online_lookup()
    assert metron_instances[0].get_calls == [42]
    assert cv_instances[0].get_calls == [1234]


def test_first_wins_continues_when_first_no_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Metron search returns nothing → CV still gets a chance with its --id."""
    metron_instances, cv_instances, factories = _dual_factories_for_first_wins()
    monkeypatch.setattr(
        ComicboxOnlineLookup,
        "_ONLINE_SOURCE_FACTORIES",
        MappingProxyType(factories),
    )
    args = Namespace(
        comicbox=Namespace(
            # No metron --id; metron falls to search and returns [].
            # CV has explicit --id, which always runs.
            explicit_ids=["comicvine:1234"],
            online_sources=["metron", "comicvine"],
            general=Namespace(
                metadata={
                    "comicbox": {"series": {"name": "Foo"}, "issue": {"name": "5"}}
                }
            ),
            auth=["metron:user=u", "metron:pass=p", "comicvine:key=k"],
        )
    )
    cb = Comicbox(config=args)
    cb.run_online_lookup()
    assert metron_instances[0].get_calls == []
    assert metron_instances[0].search_calls  # search was attempted
    assert cv_instances[0].get_calls == [1234]


def test_explicit_id_on_second_source_overrides_first_wins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Metron wins via --id; CV has its own --id → CV still runs."""
    metron_instances, cv_instances, factories = _dual_factories_for_first_wins()
    monkeypatch.setattr(
        ComicboxOnlineLookup,
        "_ONLINE_SOURCE_FACTORIES",
        MappingProxyType(factories),
    )
    args = Namespace(
        comicbox=Namespace(
            explicit_ids=["metron:42", "comicvine:1234"],
            auth=["metron:user=u", "metron:pass=p", "comicvine:key=k"],
        )
    )
    cb = Comicbox(config=args)
    cb.run_online_lookup()
    assert metron_instances[0].get_calls == [42]
    assert cv_instances[0].get_calls == [1234]


def test_stored_id_triggers_refresh_instead_of_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Comic has a stored metron id → metron.get(stored_id) runs, no search."""
    metron_instances, _cv, factories = _dual_factories_for_first_wins()
    monkeypatch.setattr(
        ComicboxOnlineLookup,
        "_ONLINE_SOURCE_FACTORIES",
        MappingProxyType(factories),
    )
    args = Namespace(
        comicbox=Namespace(
            online_sources=["metron"],
            general=Namespace(
                metadata={
                    "comicbox": {"identifiers": {"metron": {"key": "42"}}},
                }
            ),
            auth=["metron:user=u", "metron:pass=p"],
        )
    )
    cb = Comicbox(config=args)
    cb.run_online_lookup()
    assert metron_instances[0].get_calls == [42]
    assert metron_instances[0].search_calls == []


def test_force_search_overrides_stored_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--force-search ignores the stored id and runs the search path."""
    metron_instances, _cv, factories = _dual_factories_for_first_wins()
    monkeypatch.setattr(
        ComicboxOnlineLookup,
        "_ONLINE_SOURCE_FACTORIES",
        MappingProxyType(factories),
    )
    args = Namespace(
        comicbox=Namespace(
            online_sources=["metron"],
            rematch=True,
            general=Namespace(
                metadata={
                    "comicbox": {
                        "identifiers": {"metron": {"key": "42"}},
                        "series": {"name": "Foo"},
                        "issue": {"name": "5"},
                    },
                }
            ),
            auth=["metron:user=u", "metron:pass=p"],
        )
    )
    cb = Comicbox(config=args)
    cb.run_online_lookup()
    assert metron_instances[0].get_calls == []
    assert metron_instances[0].search_calls  # search ran instead of stored-id refresh


def test_explicit_id_beats_force_search(monkeypatch: pytest.MonkeyPatch) -> None:
    """--id is the strongest user signal; --force-search does not override it."""
    metron_instances, _cv, factories = _dual_factories_for_first_wins()
    monkeypatch.setattr(
        ComicboxOnlineLookup,
        "_ONLINE_SOURCE_FACTORIES",
        MappingProxyType(factories),
    )
    args = Namespace(
        comicbox=Namespace(
            explicit_ids=["metron:7"],
            rematch=True,
            general=Namespace(
                metadata={"comicbox": {"identifiers": {"metron": {"key": "42"}}}}
            ),
            auth=["metron:user=u", "metron:pass=p"],
        )
    )
    cb = Comicbox(config=args)
    cb.run_online_lookup()
    assert metron_instances[0].get_calls == [7]
    assert metron_instances[0].search_calls == []


def test_ignore_existing_with_first_wins_short_circuits_second_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Stored metron id + --ignore-existing → metron skipped but counts as a win.

    Under first-wins, that counts as a contribution: CV is also skipped
    because the user already has the file tagged from a prior source.
    """
    metron_instances, cv_instances, factories = _dual_factories_for_first_wins()
    monkeypatch.setattr(
        ComicboxOnlineLookup,
        "_ONLINE_SOURCE_FACTORIES",
        MappingProxyType(factories),
    )
    args = Namespace(
        comicbox=Namespace(
            online_sources=["metron", "comicvine"],
            rematch=True,
            general=Namespace(
                metadata={"comicbox": {"identifiers": {"metron": {"key": "42"}}}}
            ),
            auth=["metron:user=u", "metron:pass=p", "comicvine:key=k"],
        )
    )
    cb = Comicbox(config=args)
    cb.run_online_lookup()
    assert metron_instances[0].get_calls == []
    assert cv_instances[0].get_calls == []
    assert cv_instances[0].search_calls == []


def test_stored_identifier_helper_returns_none_when_unset(
    patched_metron,
) -> None:
    args = Namespace(
        comicbox=Namespace(
            online_sources=["metron"],
            general=Namespace(metadata={"comicbox": {"series": {"name": "Foo"}}}),
            auth=["metron:user=u", "metron:pass=p"],
        )
    )
    cb = Comicbox(config=args)
    # Trigger normalize so non-online sources are populated.
    cb.get_normalized_metadata(MetadataSources.CONFIG)
    assert cb._stored_identifier("metron") is None


def test_stored_identifier_helper_returns_parsed_int(patched_metron) -> None:
    args = Namespace(
        comicbox=Namespace(
            online_sources=["metron"],
            general=Namespace(
                metadata={"comicbox": {"identifiers": {"metron": {"key": "42"}}}}
            ),
            auth=["metron:user=u", "metron:pass=p"],
        )
    )
    cb = Comicbox(config=args)
    cb.get_normalized_metadata(MetadataSources.CONFIG)
    assert cb._stored_identifier("metron") == 42


# ----------------------------------------- _local_cover_phash PDF fix


def _solid_png(color: tuple[int, int, int] = (255, 0, 0), size: int = 64) -> bytes:
    img = Image.new("RGB", (size, size), color)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_local_cover_phash_passes_pixmap_format() -> None:
    """get_cover_page must be called with pdf_format='pixmap' for PDF support."""
    cb = _build_cb()
    calls: list[dict] = []

    def fake_get_cover_page(
        self, pdf_format: str = "", *, skip_metadata: bool = False
    ) -> bytes:
        calls.append({"pdf_format": pdf_format, "skip_metadata": skip_metadata})
        return _solid_png()

    with patch.object(type(cb), "get_cover_page", fake_get_cover_page):
        cb._local_cover_phash()

    assert calls, "get_cover_page was not called"
    assert calls[0]["pdf_format"] == "pixmap"
    assert calls[0]["skip_metadata"] is True


def test_local_cover_phash_succeeds_with_image_bytes() -> None:
    """Valid image bytes produce a hex pHash string."""
    cb = _build_cb()

    with patch.object(type(cb), "get_cover_page", lambda *_a, **_kw: _solid_png()):
        result = cb._local_cover_phash()

    assert isinstance(result, str)
    assert len(result) > 0


def test_local_cover_phash_fails_with_pdf_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raw PDF bytes cause a warning and return None (pre-fix regression guard)."""
    cb = _build_cb()
    raw_pdf = b"%PDF-1.4 fake pdf bytes"

    warnings: list[str] = []
    monkeypatch.setattr("comicbox.box.online_lookup.logger.warning", warnings.append)

    with patch.object(type(cb), "get_cover_page", lambda *_a, **_kw: raw_pdf):
        result = cb._local_cover_phash()

    assert result is None
    assert any("pHash failed" in w for w in warnings)


def test_local_cover_phash_returns_none_for_empty_bytes() -> None:
    """Empty cover bytes short-circuit before hashing."""
    cb = _build_cb()

    with patch.object(type(cb), "get_cover_page", lambda *_a, **_kw: b""):
        result = cb._local_cover_phash()

    assert result is None


def test_local_cover_phash_is_cached() -> None:
    """Second call returns cached result without calling get_cover_page again."""
    cb = _build_cb()
    call_count = 0

    def counting_get_cover_page(*args, **kwargs) -> bytes:
        nonlocal call_count
        call_count += 1
        return _solid_png()

    with patch.object(type(cb), "get_cover_page", counting_get_cover_page):
        first = cb._local_cover_phash()
        second = cb._local_cover_phash()

    assert first == second
    assert call_count == 1
