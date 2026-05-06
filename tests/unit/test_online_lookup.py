"""ComicboxOnlineLookup mixin tests (M2: --id path)."""

from __future__ import annotations

from argparse import Namespace
from types import MappingProxyType
from typing import TYPE_CHECKING

import pytest

from comicbox.box import Comicbox
from comicbox.box.online_lookup import ComicboxOnlineLookup
from comicbox.formats import MetadataFormats
from comicbox.sources import MetadataSources

if TYPE_CHECKING:
    from comicbox.online.profile import Candidate

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
        self._payload = payload or _SAMPLE_ISSUE

    def is_configured(self) -> bool:
        return bool(self._credentials.username and self._credentials.password)

    def get(self, issue_id: int) -> dict:
        self.get_calls.append(issue_id)
        return dict(self._payload)


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
            # No metron creds → is_configured returns False → source skipped.
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
