"""
Series-wide prefetch for Metron.

With `PAGE_SIZE=100`, a whole series is one or a few pages. When a batch
holds many comics from one series, listing it once beats one
`issues_list` per comic — but only when it actually does, which is what
the `series(id)` call establishes before committing.
"""

from __future__ import annotations

from typing import Any

import pytest

from comicbox.config.online.settings import OnlineSettings, OnlineSourceCredentials
from comicbox.formats.metron_api import online_source as metron_online_source
from comicbox.formats.metron_api.online_source import MetronOnlineSource


class _FakeBasicSeries:
    def __init__(self, sid: int, name: str = "Test Series") -> None:
        self.id = sid
        self.name = name


class _FakeBaseIssue:
    def __init__(self, issue_id: int, number: str, series_id: int = 7) -> None:
        self.id = issue_id
        self.number = number
        self.cover_date = None
        self.image = None
        self.cover_hash = None
        self.series = _FakeBasicSeries(sid=series_id)


class _FakeSeries:
    def __init__(self, issue_count: int) -> None:
        self.issue_count = issue_count


class _FakeMokkari:
    """Records the list and detail calls a prefetch makes."""

    def __init__(
        self, issues: list[_FakeBaseIssue], issue_count: int | None = 50
    ) -> None:
        self._issues = issues
        self._issue_count = issue_count
        self.issues_list_calls: list[dict[str, Any]] = []
        self.series_calls: list[int] = []

    def issues_list(self, params: dict | None = None) -> list[_FakeBaseIssue]:
        params = dict(params or {})
        self.issues_list_calls.append(params)
        number = params.get("number")
        if number is None:
            return list(self._issues)
        return [i for i in self._issues if i.number == number]

    def series(self, series_id: int) -> _FakeSeries | None:
        self.series_calls.append(series_id)
        if self._issue_count is None:
            return None
        return _FakeSeries(self._issue_count)


@pytest.fixture(autouse=True)
def _clear_prefetch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test gets its own empty process-wide prefetch store."""
    from collections import OrderedDict

    monkeypatch.setattr(metron_online_source, "_prefetch_cache", OrderedDict())


def _source(monkeypatch: pytest.MonkeyPatch, fake: _FakeMokkari) -> MetronOnlineSource:
    creds = OnlineSourceCredentials(user="u", password="p")
    src = MetronOnlineSource(creds, OnlineSettings())
    monkeypatch.setattr(src, "_get_session", lambda: fake)
    return src


def _issues() -> list[_FakeBaseIssue]:
    return [_FakeBaseIssue(100 + n, str(n)) for n in range(1, 51)]


# ------------------------------------------------------------- the win


def test_prefetch_serves_later_issues_without_more_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One list call answers the whole cluster's volume-scoped lookups."""
    fake = _FakeMokkari(_issues(), issue_count=50)
    src = _source(monkeypatch, fake)

    src.prefetch_volume(7, cluster_size=50)

    assert fake.series_calls == [7]
    assert fake.issues_list_calls == [{"series_id": 7}]

    for number in ("1", "17", "50"):
        candidate = src.lookup_issue(7, number)
        assert candidate is not None
        assert candidate.summary.issue == number
        assert candidate.volume_id == 7
    # Still one list call: every lookup came out of the prefetch.
    assert fake.issues_list_calls == [{"series_id": 7}]


def test_an_issue_the_series_does_not_have_still_asks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    A prefetch is a cache, not an oracle.

    Metron may have added the issue since, so a miss falls through to
    the per-issue lookup rather than reporting "no such issue".
    """
    fake = _FakeMokkari(_issues(), issue_count=50)
    src = _source(monkeypatch, fake)
    src.prefetch_volume(7, cluster_size=50)

    assert src.lookup_issue(7, "999") is None
    assert fake.issues_list_calls[-1] == {"series_id": 7, "number": "999"}


def test_leading_zeros_are_normalized_on_both_sides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`014` from a filename has to find Metron's unpadded `14`."""
    fake = _FakeMokkari(_issues(), issue_count=50)
    src = _source(monkeypatch, fake)
    src.prefetch_volume(7, cluster_size=50)

    candidate = src.lookup_issue(7, "014")
    assert candidate is not None
    assert candidate.summary.issue == "14"
    assert fake.issues_list_calls == [{"series_id": 7}]


# --------------------------------------------------- when NOT to do it


def test_small_clusters_are_not_worth_a_prefetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Below the floor the two setup requests cost more than they save."""
    fake = _FakeMokkari(_issues(), issue_count=50)
    src = _source(monkeypatch, fake)

    src.prefetch_volume(7, cluster_size=2)

    assert fake.series_calls == []
    assert fake.issues_list_calls == []


def test_a_long_series_for_a_short_cluster_is_declined(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    `series(id)` exists to answer this before the pages are fetched.

    900 issues is 9 pages plus the series call — more requests than the
    5 per-issue lookups it would replace, so it must not happen.
    """
    fake = _FakeMokkari(_issues(), issue_count=900)
    src = _source(monkeypatch, fake)

    src.prefetch_volume(7, cluster_size=5)

    assert fake.series_calls == [7]
    assert fake.issues_list_calls == []  # never committed to the pages


def test_a_long_series_for_a_long_cluster_is_worth_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeMokkari(_issues(), issue_count=900)
    src = _source(monkeypatch, fake)

    src.prefetch_volume(7, cluster_size=200)

    assert fake.issues_list_calls == [{"series_id": 7}]


def test_prefetch_happens_once_per_volume(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeMokkari(_issues(), issue_count=50)
    src = _source(monkeypatch, fake)

    src.prefetch_volume(7, cluster_size=50)
    src.prefetch_volume(7, cluster_size=50)

    assert fake.series_calls == [7]
    assert fake.issues_list_calls == [{"series_id": 7}]


# ---------------------------------------------------------- degradation


def test_an_unknown_issue_count_declines_quietly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No `issue_count` means no way to know the page cost."""
    fake = _FakeMokkari(_issues(), issue_count=None)
    src = _source(monkeypatch, fake)

    src.prefetch_volume(7, cluster_size=50)

    assert fake.issues_list_calls == []


def test_a_failed_prefetch_leaves_the_per_issue_path_intact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An optimization must never be able to fail a comic."""
    fake = _FakeMokkari(_issues(), issue_count=50)
    src = _source(monkeypatch, fake)

    def boom(_series_id: int) -> None:
        msg = "metron is down"
        raise RuntimeError(msg)

    monkeypatch.setattr(fake, "series", boom)

    src.prefetch_volume(7, cluster_size=50)  # must not raise

    candidate = src.lookup_issue(7, "14")
    assert candidate is not None
    assert fake.issues_list_calls == [{"series_id": 7, "number": "14"}]


def test_an_abort_during_prefetch_still_ends_the_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Degrading past a failure must not swallow the stop signal."""
    from comicbox.exceptions import OnlineLookupAbortedError

    fake = _FakeMokkari(_issues(), issue_count=50)
    src = _source(monkeypatch, fake)

    def abort(_series_id: int) -> None:
        msg = "quota exhausted"
        raise OnlineLookupAbortedError(msg)

    monkeypatch.setattr(fake, "series", abort)

    with pytest.raises(OnlineLookupAbortedError):
        src.prefetch_volume(7, cluster_size=50)


# ----------------------------------------------------------- the store


def test_the_store_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    A library run touches many series; this holds real payloads.

    Oldest-first is the right eviction here: a batch runs series by
    series, so the oldest entry belongs to the series it has finished.
    """
    monkeypatch.setattr(metron_online_source, "_PREFETCH_MAX_VOLUMES", 3)
    for volume_id in range(5):
        metron_online_source._store_prefetch(volume_id, {"1": object()})

    assert metron_online_source._has_prefetch(0) is False
    assert metron_online_source._has_prefetch(1) is False
    assert metron_online_source._has_prefetch(4) is True
