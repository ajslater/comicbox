"""ComicboxOnlineLookup mixin tests (M2: --id path)."""

from __future__ import annotations

from argparse import Namespace
from types import MappingProxyType
from typing import TYPE_CHECKING

import pytest

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
        return bool(self._credentials.username and self._credentials.password)

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


def _config_with_metron_creds(**extra) -> dict:
    return {
        "comicbox": {
            "online": {
                "metron": {"username": "u", "password": "p"},
            },
            **extra,
        }
    }


def test_lookup_disabled_when_online_off(patched_metron) -> None:
    cb = _build_cb(metadata={})
    cb.get_merged_metadata()
    assert patched_metron == []


def test_explicit_id_triggers_get(patched_metron) -> None:
    args = Namespace(
        comicbox=Namespace(
            online_sources=["metron"],
            explicit_ids=["metron:42"],
            online={"metron": {"username": "u", "password": "p"}},
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
            online={"metron": {"username": "u", "password": "p"}},
        )
    )
    cb = Comicbox(config=args)
    cb.get_merged_metadata()
    sd = cb.get_source_metadata(MetadataSources.METRON_API)
    assert sd is not None
    assert len(sd) == 1
    # The payload was wrapped under the schema's ROOT_TAG.
    assert "metron_api" in sd[0].data


def test_unconfigured_source_skipped(patched_metron) -> None:
    args = Namespace(
        comicbox=Namespace(
            online_sources=["metron"],
            explicit_ids=["metron:42"],
            # Explicitly set blank creds so the test isolates from
            # ~/.config/comicbox/config.yaml or env vars on the developer's
            # machine — otherwise is_configured() returns True and the
            # "skip unconfigured" branch we're testing never fires.
            online={"metron": {"username": "", "password": ""}},
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
            online={"metron": {"username": "u", "password": "p"}},
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
            online={"metron": {"username": "u", "password": "p"}},
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
            return False  # No api_key configured.

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
            return bool(self._credentials.api_key)

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
            online={
                "metron": {"username": "u", "password": "p"},
                "comicvine": {"api_key": "k"},
            },
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
            online={
                "metron": {"username": "u", "password": "p"},
                "comicvine": {"api_key": "k"},
            },
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
    from comicbox.box.online_lookup import _resolve_volume

    assert _resolve_volume({"comicbox": {"volume": {"number": 2}}}) == 2
    assert _resolve_volume({"comicbox": {"volume": {"number": "5"}}}) == 5


def test_resolve_volume_rejects_year_shape() -> None:
    """
    ComicInfo.xml convention uses year-of-first-issue as volume.

    Metron's `series_volume` filter expects an ordinal — sending 2019
    matches no issues. We drop year-shaped values (1900-2100) so they
    don't poison the search.
    """
    from comicbox.box.online_lookup import _resolve_volume

    assert _resolve_volume({"comicbox": {"volume": {"number": 2019}}}) is None
    assert _resolve_volume({"comicbox": {"volume": {"number": "1986"}}}) is None
    assert _resolve_volume({"comicbox": {"volume": {"number": 2100}}}) is None
    assert _resolve_volume({"comicbox": {"volume": {"number": 1900}}}) is None


def test_resolve_volume_keeps_pre_1900_values() -> None:
    """Pre-1900 volume numbers can't be year-shaped; keep them."""
    from comicbox.box.online_lookup import _resolve_volume

    assert _resolve_volume({"comicbox": {"volume": {"number": 1899}}}) == 1899
    assert _resolve_volume({"comicbox": {"volume": {"number": 50}}}) == 50


def test_resolve_volume_keeps_post_2100_values() -> None:
    """Post-2100 volume numbers can't be year-shaped (sci-fi aside); keep them."""
    from comicbox.box.online_lookup import _resolve_volume

    assert _resolve_volume({"comicbox": {"volume": {"number": 2101}}}) == 2101


def test_resolve_volume_handles_missing_or_garbage() -> None:
    from comicbox.box.online_lookup import _resolve_volume

    assert _resolve_volume({}) is None
    assert _resolve_volume({"comicbox": {}}) is None
    assert _resolve_volume({"comicbox": {"volume": {"number": "abc"}}}) is None


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
            return bool(self._credentials.api_key)

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
            online={
                "metron": {"username": "u", "password": "p"},
                "comicvine": {"api_key": "k"},
            },
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


def test_tag_all_sources_runs_both(monkeypatch: pytest.MonkeyPatch) -> None:
    """--tag-all-sources lets CV run even after metron contributed."""
    metron_instances, cv_instances, factories = _dual_factories_for_first_wins()
    monkeypatch.setattr(
        ComicboxOnlineLookup,
        "_ONLINE_SOURCE_FACTORIES",
        MappingProxyType(factories),
    )
    args = Namespace(
        comicbox=Namespace(
            explicit_ids=["metron:42", "comicvine:1234"],
            tag_all_sources=True,
            online={
                "metron": {"username": "u", "password": "p"},
                "comicvine": {"api_key": "k"},
            },
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
            metadata={"comicbox": {"series": {"name": "Foo"}, "issue": {"name": "5"}}},
            online={
                "metron": {"username": "u", "password": "p"},
                "comicvine": {"api_key": "k"},
            },
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
            online={
                "metron": {"username": "u", "password": "p"},
                "comicvine": {"api_key": "k"},
            },
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
            metadata={
                "comicbox": {"identifiers": {"metron": {"key": "42"}}},
            },
            online={"metron": {"username": "u", "password": "p"}},
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
            force_search=True,
            metadata={
                "comicbox": {
                    "identifiers": {"metron": {"key": "42"}},
                    "series": {"name": "Foo"},
                    "issue": {"name": "5"},
                },
            },
            online={"metron": {"username": "u", "password": "p"}},
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
            force_search=True,
            metadata={"comicbox": {"identifiers": {"metron": {"key": "42"}}}},
            online={"metron": {"username": "u", "password": "p"}},
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
            ignore_existing=True,
            metadata={"comicbox": {"identifiers": {"metron": {"key": "42"}}}},
            online={
                "metron": {"username": "u", "password": "p"},
                "comicvine": {"api_key": "k"},
            },
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
            metadata={"comicbox": {"series": {"name": "Foo"}}},
            online={"metron": {"username": "u", "password": "p"}},
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
            metadata={"comicbox": {"identifiers": {"metron": {"key": "42"}}}},
            online={"metron": {"username": "u", "password": "p"}},
        )
    )
    cb = Comicbox(config=args)
    cb.get_normalized_metadata(MetadataSources.CONFIG)
    assert cb._stored_identifier("metron") == 42
