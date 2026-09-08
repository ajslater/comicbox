"""
Online source-failure degradation tests.

The online engine is built to survive a flaky upstream: a source that
raises mid-lookup logs a warning and degrades to "no metadata from this
source", never taking the run down with it. The one exception is
`OnlineLookupAbortedError`, which is a decision about the *run* (the
user answered "abort", or a caller cancelled a retry sleep) and must
propagate through every handler.

Three failure surfaces are covered here:

* `_run_search` — `source.search()` raising.
* `_try_series_cache_lookup` — the box-level guard around
  `source.lookup_issue()`.
* `OnlineSource.lookup_issue` — the base-class wrapper around
  `_lookup_issue_in_volume`. `tests/unit/test_series_cache.py` overrides
  `lookup_issue` wholesale, so that wrapper never runs there.
"""

from __future__ import annotations

from argparse import Namespace
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import pytest
from loguru import logger
from typing_extensions import override

from comicbox.box import Comicbox
from comicbox.box.online_lookup import ComicboxOnlineLookup, _series_fingerprint
from comicbox.config import get_config
from comicbox.config.online.settings import OnlineSourceCredentials
from comicbox.exceptions import OnlineLookupAbortedError
from comicbox.formats import MetadataFormats
from comicbox.formats.base.online import outcome_stats
from comicbox.formats.base.online.profile import (
    Candidate,
    CandidateSummary,
    ComicProfile,
)
from comicbox.formats.base.online.sources.base import OnlineSource
from comicbox.formats.sources import MetadataSources

if TYPE_CHECKING:
    from collections.abc import Iterator

SERIES = "Foo Comics"
PUBLISHER = "Quality Comics"
YEAR = 2020
VOLUME_ID = 42


@pytest.fixture(autouse=True)
def _reset_outcome_stats() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Counters are a process-wide singleton; isolate every test."""
    outcome_stats.reset()
    yield
    outcome_stats.reset()


@pytest.fixture
def warnings() -> Iterator[list[str]]:
    """Capture loguru WARNING-and-above messages."""
    messages: list[str] = []
    handler_id = logger.add(messages.append, level="WARNING", format="{message}")
    try:
        yield messages
    finally:
        logger.remove(handler_id)


# --- mock sources -----------------------------------------------------------


def _issue_payload(issue_id: int) -> dict:
    return {
        "id": issue_id,
        "number": "5",
        "cover_date": "2020-04-01",
        "modified": "2020-04-02T12:00:00Z",
        "publisher": {"id": 1, "name": "Online Publisher"},
        "series": {"id": 1, "name": "Online Series", "year_began": 2020, "volume": 1},
    }


def _make_candidate(
    issue_id: int = 101, volume_id: int | None = VOLUME_ID
) -> Candidate:
    return Candidate(
        source="metron",
        issue_id=issue_id,
        summary=CandidateSummary(
            series=SERIES,
            issue="5",
            year=YEAR,
            publisher=PUBLISHER,
            page_count=24,
            cover_url=None,
            variant_label=None,
        ),
        volume_id=volume_id,
    )


class _FlakyMetron:
    """Mock source whose `search`/`lookup_issue` raise on demand."""

    name = "metron"
    metadata_source = MetadataSources.METRON_API
    metadata_format = MetadataFormats.METRON_API

    def __init__(
        self,
        credentials,
        settings,
        *,
        search_exc: BaseException | None = None,
        lookup_exc: BaseException | None = None,
    ) -> None:
        self._credentials = credentials
        self._settings = settings
        self.search_exc = search_exc
        self.lookup_exc = lookup_exc
        self.search_calls = 0
        self.lookup_calls: list[tuple[int, str | None]] = []
        self.get_calls: list[int] = []

    def is_configured(self) -> bool:
        return True

    def get(self, issue_id: int) -> dict:
        self.get_calls.append(issue_id)
        return _issue_payload(issue_id)

    def search(self, profile) -> list[Candidate]:
        self.search_calls += 1
        if self.search_exc is not None:
            raise self.search_exc
        return [_make_candidate()]

    def lookup_issue(
        self, volume_id: int, issue_number: str | None
    ) -> Candidate | None:
        self.lookup_calls.append((volume_id, issue_number))
        if self.lookup_exc is not None:
            raise self.lookup_exc
        return _make_candidate()


class _WrapperMetron(OnlineSource):
    """
    A real `OnlineSource` so the base `lookup_issue` wrapper runs.

    The mocks above replace `lookup_issue` outright, which is exactly
    what leaves `sources/base.py`'s failure semantics untested.
    """

    name = "metron"
    metadata_source = MetadataSources.METRON_API
    metadata_format = MetadataFormats.METRON_API

    def __init__(
        self,
        credentials,
        settings,
        *,
        lookup_exc: BaseException | None = None,
        implement_fast_path: bool = True,
    ) -> None:
        super().__init__(credentials, settings)
        self.lookup_exc = lookup_exc
        self.implement_fast_path = implement_fast_path
        self.search_calls = 0
        self.get_calls: list[int] = []

    @override
    def is_configured(self) -> bool:
        return True

    @override
    def get(self, issue_id: int) -> dict[str, Any]:
        self.get_calls.append(issue_id)
        return _issue_payload(issue_id)

    @override
    def search(self, profile: ComicProfile) -> list[Candidate]:
        self.search_calls += 1
        return [_make_candidate()]

    @override
    def _lookup_issue_in_volume(
        self, volume_id: int, issue_number: str | None
    ) -> Candidate | None:
        if not self.implement_fast_path:
            return super()._lookup_issue_in_volume(volume_id, issue_number)
        if self.lookup_exc is not None:
            raise self.lookup_exc
        return _make_candidate()


def _patch_factory(monkeypatch: pytest.MonkeyPatch, build) -> list:
    instances: list = []

    def factory(creds, settings):
        src = build(creds, settings)
        instances.append(src)
        return src

    monkeypatch.setattr(
        ComicboxOnlineLookup,
        "_ONLINE_SOURCE_FACTORIES",
        MappingProxyType({"metron": factory}),
    )
    return instances


def _cli_metadata() -> dict:
    return {
        "comicbox": {
            "series": {"name": SERIES},
            "issue": {"name": "5"},
            "date": {"year": YEAR},
            "publisher": {"name": PUBLISHER},
            "page_count": 24,
        }
    }


def _build_cb() -> Comicbox:
    args = Namespace(
        comicbox=Namespace(
            online_sources=["metron"],
            general=Namespace(metadata=_cli_metadata()),
            auth=["metron:user=u", "metron:pass=p"],
        )
    )
    return Comicbox(config=args)


def _warm_cache() -> dict:
    fp = _series_fingerprint(
        ComicProfile(series=SERIES, year=YEAR, publisher=PUBLISHER)
    )
    return {("metron", fp): VOLUME_ID}


def _assert_untouched(cb: Comicbox) -> None:
    """Assert no online metadata leaked into the merge."""
    md = cb.get_merged_metadata()["comicbox"]
    assert md["series"]["name"] == SERIES
    assert md["publisher"]["name"] == PUBLISHER
    assert "metron" not in md.get("identifiers", {})


def _assert_applied(cb: Comicbox) -> None:
    """Assert the fallback search landed — the online payload won the merge."""
    md = cb.get_merged_metadata()["comicbox"]
    assert md["series"]["name"] == "Online Series"
    assert md["publisher"]["name"] == "Online Publisher"
    assert md["identifiers"]["metron"]["key"] == "101"


# --- search() failures ------------------------------------------------------


def test_search_generic_exception_degrades(warnings: list[str]) -> None:
    """A flaky upstream costs this source's contribution, not the run."""

    def build(creds, settings):
        return _FlakyMetron(creds, settings, search_exc=RuntimeError("upstream 500"))

    cb = _build_cb()
    with pytest.MonkeyPatch.context() as mp:
        instances = _patch_factory(mp, build)
        assert cb.run_online_lookup() is False
        assert any("search failed: upstream 500" in m for m in warnings)
        assert instances[0].get_calls == []
        _assert_untouched(cb)


def test_search_generic_exception_records_no_outcome_bucket() -> None:
    """
    A source-side error is not a resolution outcome.

    `_run_search` returns before the matcher runs, so nothing lands in
    auto-write / skip / no-match / prompt. The end-of-run summary stays
    silent rather than reporting a fake "no-match".
    """

    def build(creds, settings):
        return _FlakyMetron(creds, settings, search_exc=RuntimeError("boom"))

    cb = _build_cb()
    with pytest.MonkeyPatch.context() as mp:
        _patch_factory(mp, build)
        cb.run_online_lookup()
    assert outcome_stats.has_any_activity() is False
    assert outcome_stats.summary_lines() == []


def test_search_not_implemented_error_degrades(warnings: list[str]) -> None:
    """`NotImplementedError` has no special meaning on the search path."""

    def build(creds, settings):
        return _FlakyMetron(
            creds, settings, search_exc=NotImplementedError("no search")
        )

    cb = _build_cb()
    with pytest.MonkeyPatch.context() as mp:
        _patch_factory(mp, build)
        assert cb.run_online_lookup() is False
    assert any("search failed" in m for m in warnings)
    assert outcome_stats.has_any_activity() is False


def test_search_abort_propagates(warnings: list[str]) -> None:
    """Abort is about the run; it must not be degraded into a skip."""

    def build(creds, settings):
        return _FlakyMetron(
            creds, settings, search_exc=OnlineLookupAbortedError("cancelled")
        )

    cb = _build_cb()
    with pytest.MonkeyPatch.context() as mp:
        _patch_factory(mp, build)
        with pytest.raises(OnlineLookupAbortedError):
            cb.run_online_lookup()
    assert not any("search failed" in m for m in warnings)
    assert outcome_stats.has_any_activity() is False


# --- lookup_issue() failures at the box guard -------------------------------


def test_series_cache_lookup_exception_falls_back_to_search(
    warnings: list[str],
) -> None:
    """A warm-path failure is recoverable: the cold search still runs."""

    def build(creds, settings):
        return _FlakyMetron(creds, settings, lookup_exc=RuntimeError("volume 503"))

    cb = _build_cb()
    cb.set_series_cache(_warm_cache())
    with pytest.MonkeyPatch.context() as mp:
        instances = _patch_factory(mp, build)
        assert cb.run_online_lookup() is True
    src = instances[0]
    assert src.lookup_calls == [(VOLUME_ID, "5")]
    assert src.search_calls == 1
    assert any(
        "series-cache lookup_issue" in m and "falling back to search" in m
        for m in warnings
    )
    # The recovered run still books its real outcome.
    assert "1 auto-written" in "\n".join(outcome_stats.summary_lines())
    _assert_applied(cb)


def test_series_cache_lookup_and_search_both_fail(warnings: list[str]) -> None:
    """Both legs down → no metadata, no crash, no outcome bucket."""

    def build(creds, settings):
        return _FlakyMetron(
            creds,
            settings,
            lookup_exc=RuntimeError("volume 503"),
            search_exc=RuntimeError("search 503"),
        )

    cb = _build_cb()
    cb.set_series_cache(_warm_cache())
    with pytest.MonkeyPatch.context() as mp:
        _patch_factory(mp, build)
        assert cb.run_online_lookup() is False
    assert any("series-cache lookup_issue" in m for m in warnings)
    assert any("search failed: search 503" in m for m in warnings)
    assert outcome_stats.has_any_activity() is False
    _assert_untouched(cb)


def test_series_cache_lookup_abort_propagates() -> None:
    """The warm path must not swallow an abort into a search fallback."""

    def build(creds, settings):
        return _FlakyMetron(
            creds, settings, lookup_exc=OnlineLookupAbortedError("cancelled")
        )

    cb = _build_cb()
    cb.set_series_cache(_warm_cache())
    with pytest.MonkeyPatch.context() as mp:
        instances = _patch_factory(mp, build)
        with pytest.raises(OnlineLookupAbortedError):
            cb.run_online_lookup()
    assert instances[0].search_calls == 0
    assert outcome_stats.has_any_activity() is False


def test_series_cache_lookup_not_implemented_falls_back_quietly(
    warnings: list[str],
) -> None:
    """A source without the fast path is normal, so it isn't a warning."""

    def build(creds, settings):
        return _FlakyMetron(creds, settings, lookup_exc=NotImplementedError())

    cb = _build_cb()
    cb.set_series_cache(_warm_cache())
    with pytest.MonkeyPatch.context() as mp:
        instances = _patch_factory(mp, build)
        assert cb.run_online_lookup() is True
    assert instances[0].search_calls == 1
    assert not any("lookup_issue" in m for m in warnings)


# --- the OnlineSource.lookup_issue wrapper ----------------------------------


def _wrapper_source(**kwargs) -> _WrapperMetron:
    cfg = get_config(Namespace(comicbox=Namespace()))
    creds = OnlineSourceCredentials(user="u", password="p")
    return _WrapperMetron(creds, cfg.online, **kwargs)


def test_wrapper_degrades_source_errors_to_none(warnings: list[str]) -> None:
    """Base-class contract: source-side errors log and fall back to search."""
    src = _wrapper_source(lookup_exc=RuntimeError("gateway timeout"))
    assert src.lookup_issue(VOLUME_ID, "5") is None
    assert any(
        f"lookup_issue(volume_id={VOLUME_ID}, number='5') failed: gateway timeout" in m
        for m in warnings
    )


def test_wrapper_propagates_abort() -> None:
    src = _wrapper_source(lookup_exc=OnlineLookupAbortedError("cancelled"))
    with pytest.raises(OnlineLookupAbortedError):
        src.lookup_issue(VOLUME_ID, "5")


def test_wrapper_propagates_not_implemented() -> None:
    """Callers detect "no fast path" by catching NotImplementedError."""
    src = _wrapper_source(lookup_exc=NotImplementedError())
    with pytest.raises(NotImplementedError):
        src.lookup_issue(VOLUME_ID, "5")


def test_wrapper_default_implementation_is_not_implemented() -> None:
    """A source that never overrides `_lookup_issue_in_volume` opts out."""
    src = _wrapper_source(implement_fast_path=False)
    with pytest.raises(NotImplementedError):
        src.lookup_issue(VOLUME_ID, "5")


def test_wrapper_passes_a_hit_through() -> None:
    src = _wrapper_source()
    candidate = src.lookup_issue(VOLUME_ID, "5")
    assert candidate is not None
    assert candidate.issue_id == 101


def test_wrapper_failure_degrades_through_the_box(warnings: list[str]) -> None:
    """
    End-to-end: the base wrapper's `None` is a cache miss to the box.

    The box logs its "returned no match" info line rather than its own
    warning, because the wrapper already absorbed the exception.
    """

    def build(creds, settings):
        return _WrapperMetron(creds, settings, lookup_exc=RuntimeError("gateway"))

    cb = _build_cb()
    cb.set_series_cache(_warm_cache())
    with pytest.MonkeyPatch.context() as mp:
        instances = _patch_factory(mp, build)
        assert cb.run_online_lookup() is True
    assert instances[0].search_calls == 1
    assert any("lookup_issue(volume_id=42" in m for m in warnings)
    assert not any("series-cache lookup_issue" in m for m in warnings)
    _assert_applied(cb)


def test_wrapper_abort_propagates_through_the_box() -> None:
    """An abort raised inside `_lookup_issue_in_volume` ends the run."""

    def build(creds, settings):
        return _WrapperMetron(
            creds, settings, lookup_exc=OnlineLookupAbortedError("cancelled")
        )

    cb = _build_cb()
    cb.set_series_cache(_warm_cache())
    with pytest.MonkeyPatch.context() as mp:
        instances = _patch_factory(mp, build)
        with pytest.raises(OnlineLookupAbortedError):
            cb.run_online_lookup()
    assert instances[0].search_calls == 0


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
