"""
MetronOnlineSource search-flow tests.

Exercises the search: ``issues_list({series_name, number, cover_year,
series_volume})`` directly, with no separate series-discovery step, plus
the single wide ``cover_date_range_*`` fallback that replaces the old
six-call miss cascade. Since mokkari 3.28.0 / Metron server commit
3b1e46b, `BaseIssue.series.id` is populated on list results, so
`Candidate.volume_id` resolves straight from the search result too. Mocks
`_get_session` so we never hit the network.
"""

from __future__ import annotations

from typing import Any

import pytest
from mokkari.exceptions import (
    ApiError,
    AuthenticationError,
    CacheError,
    RateLimitError,
)
from requests import Response
from requests.exceptions import HTTPError
from typing_extensions import override

from comicbox.config.online.settings import OnlineSettings, OnlineSourceCredentials
from comicbox.formats.base.online.profile import ComicProfile
from comicbox.formats.base.online.retry import (
    _RATE_LIMIT_SCHEDULE,
    RetryCategory,
    with_retry,
)
from comicbox.formats.metron_api.online_source import MetronOnlineSource


class _FakeBaseSeries:
    def __init__(self, sid: int, name: str, volume: int = 1) -> None:
        self.id = sid
        self.name = name
        # mokkari's `BasicSeries.volume` is a required int, not optional.
        # The wide fallback ranks rows by it, so the fake has to have one.
        self.volume = volume


class _FakeBaseIssue:
    def __init__(
        self,
        iid: int,
        number: str,
        series_name: str,
        cover_year: int = 1952,
        series_id: int = 999,
        series_volume: int = 1,
    ) -> None:
        from datetime import date

        self.id = iid
        self.number = number
        self.cover_date = date(cover_year, 1, 1)
        self.image = f"https://example.com/issue/{iid}.jpg"
        # No `resource_url`: mokkari's `BaseIssue` carries none, so the
        # candidate url has to be derived from the id.
        self.cover_hash = None
        # mokkari `BaseIssue.series` is `BasicSeries` — since mokkari 3.28.0
        # / Metron server commit 3b1e46b it carries a real `.id` alongside
        # `name`, not just a sparse name-only stub.
        self.series = _FakeBaseSeries(
            sid=series_id, name=series_name, volume=series_volume
        )


def _years_requested(params: dict[str, Any]) -> set[int] | None:
    """
    Cover years a call constrains itself to, or None for no constraint.

    Metron accepts either `cover_year` (the exact call) or the
    `cover_date_range_after` / `_before` pair (the wide fallback), and
    filters on neither when given neither.
    """
    cover_year = params.get("cover_year")
    if cover_year is not None:
        return {int(cover_year)}
    after = params.get("cover_date_range_after")
    before = params.get("cover_date_range_before")
    if after and before:
        return set(range(int(str(after)[:4]), int(str(before)[:4]) + 1))
    return None


class _FakeMokkari:
    """
    Mock mokkari.Session that records the calls it receives.

    ``issues_by_key`` is keyed by whatever identifier a call actually
    sends — the ``series_name`` string for the by-name search path, or the
    ``series_id`` int for the `--series-id` fast path / volume-scoped
    lookup. There's no `series_list` method: production code no longer
    calls it.
    """

    def __init__(self, issues_by_key: dict[Any, list[_FakeBaseIssue]]) -> None:
        self._issues_by_key = issues_by_key
        self.issues_list_calls: list[dict[str, Any]] = []

    def issues_list(self, params: dict | None = None) -> list[_FakeBaseIssue]:
        params = dict(params or {})
        self.issues_list_calls.append(params)
        key = params.get("series_name")
        if key is None:
            key = params.get("series_id")
        if key is None:
            return []
        return list(self._issues_by_key.get(key, []))


def _make_metron_source(
    monkeypatch: pytest.MonkeyPatch, fake: _FakeMokkari
) -> MetronOnlineSource:
    creds = OnlineSourceCredentials(user="u", password="p")
    settings = OnlineSettings()
    src = MetronOnlineSource(creds, settings)
    monkeypatch.setattr(src, "_get_session", lambda: fake)
    return src


@pytest.mark.parametrize(
    ("user", "password", "key", "expected"),
    [
        (None, None, "t", True),  # API token alone
        ("u", "p", None, True),  # basic auth alone
        ("u", "p", "t", True),  # both; mokkari prefers the token
        (None, None, None, False),
        ("u", None, None, False),  # half a basic-auth pair
        (None, "p", None, False),
    ],
)
def test_is_configured(
    user: str | None, password: str | None, key: str | None, *, expected: bool
) -> None:
    creds = OnlineSourceCredentials(user=user, password=password, key=key)
    src = MetronOnlineSource(creds, OnlineSettings())
    assert src.is_configured() is expected


def test_search_returns_empty_with_no_series(monkeypatch: pytest.MonkeyPatch) -> None:
    """Profile without a series name skips the API entirely."""
    fake = _FakeMokkari(issues_by_key={})
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(issue="7", issue_int=7, year=1952)
    assert src.search(profile) == []
    assert fake.issues_list_calls == []


def test_search_issues_list_uses_series_name_directly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """search() calls issues_list(series_name=...) directly, no discovery step."""
    issues = {
        "GI Joe": [
            _FakeBaseIssue(iid=5001, number="7", series_name="G.I. Joe", series_id=100)
        ],
    }
    fake = _FakeMokkari(issues_by_key=issues)
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(series="GI Joe", issue="007", issue_int=7, year=1952)
    candidates = src.search(profile)

    assert len(fake.issues_list_calls) == 1
    call = fake.issues_list_calls[0]
    assert call["series_name"] == "GI Joe"
    assert call["number"] == "7"  # leading zeros stripped
    assert call["cover_year"] == 1952

    assert [c.issue_id for c in candidates] == [5001]
    # Series name on the candidate comes straight from BaseIssue.series.name.
    assert candidates[0].summary.series == "G.I. Joe"
    # volume_id comes straight from BaseIssue.series.id (mokkari 3.28.0+) —
    # no discovery step needed to resolve it.
    assert candidates[0].volume_id == 100
    # mokkari's `BasicSeries` (search results) has no `alt_names` — only
    # `IssueSeries` on the issue-detail response does — so search
    # candidates carry no alternative series names. Getting them would
    # cost an extra `series()` call per candidate.
    assert candidates[0].summary.alt_series == ()


def test_search_primary_failure_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    """A hard failure on the year-exact call raises, not returns []."""

    class _FailingMokkari(_FakeMokkari):
        @override
        def issues_list(self, params: dict | None = None) -> list[_FakeBaseIssue]:
            self.issues_list_calls.append(dict(params or {}))
            msg = "boom"
            raise ValueError(msg)

    fake = _FailingMokkari(issues_by_key={})
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(series="X", issue="1", issue_int=1, year=2020)
    with pytest.raises(ValueError, match="boom"):
        src.search(profile)


def test_search_wide_fallback_failure_reads_as_no_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    A failure in the fallback degrades; it does not fail the search.

    The exact call keeps the raise-on-failure contract — a hard failure
    there means the search failed, not that Metron has nothing — but the
    fallback is an extra chance, so losing it is a miss, mirroring what
    the per-year retries used to swallow.
    """

    class _FlakyWideMokkari(_FakeMokkari):
        @override
        def issues_list(self, params: dict | None = None) -> list[_FakeBaseIssue]:
            params = dict(params or {})
            self.issues_list_calls.append(params)
            if "cover_date_range_after" in params:
                msg = "boom on the wide call"
                raise ValueError(msg)
            return []

    fake = _FlakyWideMokkari(issues_by_key={})
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(series="Foo", issue="1", issue_int=1, year=2020)

    assert src.search(profile) == []
    assert len(fake.issues_list_calls) == 2


def test_search_retries_per_call_on_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Per-call retry honors the server's retry_after and replays the call.

    Before this fix, a `RateLimitError` from mokkari was caught by the old
    per-series fan-out's `except Exception: continue` and silently dropped
    that series' issue data. With `@with_retry()` on
    `_issues_list_with_retry`, the retry decorator catches the error,
    sleeps the hinted duration, and replays the same call.
    """
    issues = {
        "A": [_FakeBaseIssue(iid=5001, number="1", series_name="A", series_id=100)],
    }

    class _RateLimitedMokkari(_FakeMokkari):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._fail_count = 0

        @override
        def issues_list(self, params: dict | None = None) -> list[_FakeBaseIssue]:
            if self._fail_count < 1:
                # Record the failed attempt too so we can assert retry count.
                self.issues_list_calls.append(dict(params or {}))
                self._fail_count += 1
                # Real mokkari exception: `classify_retry_exception` keys on
                # the type, and the tiny `retry_after` hint keeps the real
                # sleep path fast.
                msg = "Rate limit exceeded"
                raise RateLimitError(msg, retry_after=0.001)
            return super().issues_list(params)

    fake = _RateLimitedMokkari(issues_by_key=issues)
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(series="A", issue="1", issue_int=1)
    candidates = src.search(profile)
    # The retry succeeded — we got the issue (before the fix, the
    # rate-limit error was swallowed by `except Exception: continue`
    # and the candidate list was empty).
    assert [c.issue_id for c in candidates] == [5001]
    # Two issues_list calls happened: the rate-limited one + the replay.
    assert len(fake.issues_list_calls) == 2


# ---------------------------------------------------------- --series-id


def _make_metron_source_with_series_id(
    monkeypatch: pytest.MonkeyPatch, fake: _FakeMokkari, series_id: int
) -> MetronOnlineSource:
    from comicbox.config.online.settings import OnlineLookupSettings

    creds = OnlineSourceCredentials(user="u", password="p")
    settings = OnlineSettings(
        lookup=OnlineLookupSettings(series_ids={"metron": series_id})
    )
    src = MetronOnlineSource(creds, settings)
    monkeypatch.setattr(src, "_get_session", lambda: fake)
    return src


def test_series_id_skips_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--series-id metron:NNN goes straight to a single issues_list call."""
    issues = {
        200: [
            _FakeBaseIssue(iid=9001, number="7", series_name="Bypassed", series_id=200)
        ]
    }
    fake = _FakeMokkari(issues_by_key=issues)
    src = _make_metron_source_with_series_id(monkeypatch, fake, series_id=200)
    profile = ComicProfile(series="GI Joe", issue="007", issue_int=7, year=1952)
    candidates = src.search(profile)

    assert len(fake.issues_list_calls) == 1
    call = fake.issues_list_calls[0]
    assert call["series_id"] == 200
    assert call["number"] == "7"  # leading zeros stripped
    assert call["cover_year"] == 1952
    assert [c.issue_id for c in candidates] == [9001]


def test_series_id_works_without_profile_series(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When --series-id is set, missing profile.series is fine."""
    issues = {
        300: [_FakeBaseIssue(iid=9002, number="1", series_name="Direct", series_id=300)]
    }
    fake = _FakeMokkari(issues_by_key=issues)
    src = _make_metron_source_with_series_id(monkeypatch, fake, series_id=300)
    profile = ComicProfile(issue="1", issue_int=1)  # no series at all
    candidates = src.search(profile)
    assert [c.issue_id for c in candidates] == [9002]


def test_to_candidate_propagates_series_id_from_search_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """By-name search candidates carry volume_id straight from BaseIssue.series.id."""
    issues = {
        "Watchmen": [
            _FakeBaseIssue(
                iid=27650, number="5", series_name="Watchmen", series_id=10455
            )
        ],
    }
    fake = _FakeMokkari(issues_by_key=issues)
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(series="Watchmen", issue="5", issue_int=5, year=1987)
    [cand] = src.search(profile)
    assert cand.volume_id == 10455


def test_to_candidate_url_is_metron_issue_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Candidates link to Metron's public page for the issue.

    mokkari's `BaseIssue` carries no url, so the link is derived from the
    issue id. Metron redirects the numeric-id path to the slug url.
    """
    issues = {
        "Watchmen": [
            _FakeBaseIssue(
                iid=27650, number="5", series_name="Watchmen", series_id=10455
            )
        ],
    }
    fake = _FakeMokkari(issues_by_key=issues)
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(series="Watchmen", issue="5", issue_int=5, year=1987)
    [cand] = src.search(profile)
    assert cand.url == "https://metron.cloud/issue/27650"


def test_to_candidate_propagates_series_id_from_series_id_fastpath(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--series-id metron:NNN candidates also carry the series id."""
    # `series_id=999` on the fake issue itself deliberately mismatches the
    # explicit `series_id=77` supplied to the fast path, so the assertion
    # below proves the explicit id wins over `BaseIssue.series.id`.
    issues = {
        77: [
            _FakeBaseIssue(iid=9001, number="7", series_name="Bypassed", series_id=999)
        ]
    }
    fake = _FakeMokkari(issues_by_key=issues)
    src = _make_metron_source_with_series_id(monkeypatch, fake, series_id=77)
    profile = ComicProfile(series="X", issue="7", issue_int=7, year=1952)
    [cand] = src.search(profile)
    assert cand.volume_id == 77


# ---------------------------------------------------------- ±1 year retry


class _YearAwareMokkari(_FakeMokkari):
    """
    `issues_list` honors `cover_year` AND the wide `cover_date_range_*` pair.

    Both have to work, because a miss now falls through from the exact
    call to one range call rather than to two more exact ones.
    """

    def __init__(
        self,
        issues_by_name_and_year: dict[tuple[str, int], list[_FakeBaseIssue]],
    ) -> None:
        super().__init__(issues_by_key={})
        self._issues_by_name_and_year = issues_by_name_and_year

    @override
    def issues_list(self, params: dict | None = None) -> list[_FakeBaseIssue]:
        params = dict(params or {})
        self.issues_list_calls.append(params)
        name = params.get("series_name")
        if name is None:
            return []
        years = _years_requested(params)
        rows: list[_FakeBaseIssue] = []
        for (key_name, key_year), issues in self._issues_by_name_and_year.items():
            if key_name != name:
                continue
            if years is not None and key_year not in years:
                continue
            rows.extend(issues)
        return rows


def test_wide_fallback_on_miss_finds_at_year_minus_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Year-exact returns nothing → the one range call covers Y-1."""
    issues_by_year = {
        ("Foo", 2019): [
            _FakeBaseIssue(
                iid=900, number="1", series_name="Foo", cover_year=2019, series_id=100
            )
        ],
    }
    fake = _YearAwareMokkari(issues_by_name_and_year=issues_by_year)
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(series="Foo", issue="1", issue_int=1, year=2020)
    candidates = src.search(profile)

    assert [c.issue_id for c in candidates] == [900]
    # Two calls, not three: the exact one, then one range call spanning
    # Y-1..Y+1 in place of the old two separate retries.
    assert len(fake.issues_list_calls) == 2
    assert fake.issues_list_calls[0]["cover_year"] == 2020
    assert "cover_year" not in fake.issues_list_calls[1]


def test_wide_fallback_on_miss_finds_at_year_plus_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same one range call covers Y+1; there is no second retry."""
    issues_by_year = {
        ("Foo", 2021): [
            _FakeBaseIssue(
                iid=901, number="1", series_name="Foo", cover_year=2021, series_id=100
            )
        ],
    }
    fake = _YearAwareMokkari(issues_by_name_and_year=issues_by_year)
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(series="Foo", issue="1", issue_int=1, year=2020)
    candidates = src.search(profile)

    assert [c.issue_id for c in candidates] == [901]
    assert len(fake.issues_list_calls) == 2


def test_wide_fallback_sends_a_three_year_cover_date_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fallback's exact params: name + number + Y-1..Y+1, no volume."""
    fake = _YearAwareMokkari(issues_by_name_and_year={})
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(series="Foo", issue="007", issue_int=7, year=2020, volume=3)

    assert src.search(profile) == []

    assert len(fake.issues_list_calls) == 2
    wide = fake.issues_list_calls[1]
    assert wide == {
        "series_name": "Foo",
        "number": "7",
        "cover_date_range_after": "2019-01-01",
        "cover_date_range_before": "2021-12-31",
    }


def test_year_exact_hit_does_not_trigger_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When year-exact returns candidates, no Y±1 calls are made."""
    issues_by_year = {
        ("Foo", 2020): [
            _FakeBaseIssue(
                iid=900, number="1", series_name="Foo", cover_year=2020, series_id=100
            )
        ],
    }
    fake = _YearAwareMokkari(issues_by_name_and_year=issues_by_year)
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(series="Foo", issue="1", issue_int=1, year=2020)
    candidates = src.search(profile)

    assert [c.issue_id for c in candidates] == [900]
    years_tried = [c.get("cover_year") for c in fake.issues_list_calls]
    assert years_tried == [2020]  # no retries


def test_no_year_and_no_volume_means_no_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    With nothing to relax, the fallback would repeat call 1 verbatim.

    Call 1 was already name + number: no year to widen into a range, no
    volume to drop. Sending it again would spend a request to receive the
    same empty answer.
    """
    fake = _YearAwareMokkari(issues_by_name_and_year={})
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(series="Foo", issue="1", issue_int=1)  # no year, no volume
    candidates = src.search(profile)

    assert candidates == []
    assert len(fake.issues_list_calls) == 1
    assert "cover_year" not in fake.issues_list_calls[0]


def test_no_issue_number_means_no_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    A number-less miss stops at one call. Deliberately not parity.

    The old cascade ran in full here. A wide call with only a series name
    and a three-year window paginates every issue of every series whose
    name matches, and the matcher has no issue number to pick between
    those rows with anyway.
    """
    fake = _YearAwareMokkari(issues_by_name_and_year={})
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(series="Foo", year=2020, volume=2)  # no issue number

    assert src.search(profile) == []
    assert len(fake.issues_list_calls) == 1


# ---------------------------------------------------------- volume filter


def _key_answers(
    key: tuple, *, ident: Any, years: set[int] | None, vol: int | None
) -> bool:
    """Whether a `_VolumeAwareMokkari` fixture key answers this query."""
    key_ident, key_year, key_vol = key
    if key_ident != ident or key_vol != vol:
        return False
    return years is None or key_year is None or key_year in years


class _VolumeAwareMokkari(_FakeMokkari):
    """
    Honor `series_name`/`series_id`, `series_volume`, and `cover_year` filters.

    Used to test both the volume soft-filter and the wide fallback that
    drops it, across the by-name search path and the `--series-id` fast
    path.
    """

    def __init__(
        self,
        # Keyed by (series_name_or_id, cover_year, series_volume_or_None).
        # `dict[tuple, ...]` is intentionally loose so test fixtures don't
        # need matching annotations on every literal tuple.
        issues_by_match: dict[tuple, list[_FakeBaseIssue]],
    ) -> None:
        super().__init__(issues_by_key={})
        self._issues_by_match = issues_by_match

    @override
    def issues_list(self, params: dict | None = None) -> list[_FakeBaseIssue]:
        params = dict(params or {})
        self.issues_list_calls.append(params)
        ident = params.get("series_name", params.get("series_id"))
        if ident is None:
            return []
        years = _years_requested(params)
        raw_vol = params.get("series_volume")
        vol = int(raw_vol) if raw_vol is not None else None
        rows: list[_FakeBaseIssue] = []
        for key, issues in self._issues_by_match.items():
            if _key_answers(key, ident=ident, years=years, vol=vol):
                rows.extend(issues)
        return rows


def test_volume_filter_passed_to_metron(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`profile.volume` is passed as `series_volume` on the first pass."""
    issues = {
        ("Spider-Man", 2020, 2): [
            _FakeBaseIssue(
                iid=400,
                number="1",
                series_name="Spider-Man",
                cover_year=2020,
                series_id=100,
            )
        ],
    }
    fake = _VolumeAwareMokkari(issues_by_match=issues)
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(
        series="Spider-Man", issue="1", issue_int=1, year=2020, volume=2
    )
    candidates = src.search(profile)

    assert [c.issue_id for c in candidates] == [400]
    # First (and only) call carried both filters.
    assert len(fake.issues_list_calls) == 1
    call = fake.issues_list_calls[0]
    assert call["series_volume"] == 2
    assert call["cover_year"] == 2020


def test_wide_fallback_drops_a_wrong_volume_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Wrong `Vol. N` in the filename → the fallback finds it anyway.

    Filename-parsed volumes are inconsistent: some scanners drop them,
    some get the number wrong. The old shape spent three requests proving
    the volume was wrong before trying without it; the fallback drops it
    on the one call it makes.
    """
    # Match exists at series_volume=None (i.e. unfiltered), NOT 2.
    issues = {
        ("Spider-Man", 2020, None): [
            _FakeBaseIssue(
                iid=500,
                number="1",
                series_name="Spider-Man",
                cover_year=2020,
                series_id=100,
            )
        ],
    }
    fake = _VolumeAwareMokkari(issues_by_match=issues)
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(
        series="Spider-Man", issue="1", issue_int=1, year=2020, volume=2
    )
    candidates = src.search(profile)

    assert [c.issue_id for c in candidates] == [500]
    # Two calls: exact (with the volume) then wide (without it).
    assert len(fake.issues_list_calls) == 2
    assert fake.issues_list_calls[0]["series_volume"] == 2
    assert "series_volume" not in fake.issues_list_calls[1]


def test_no_year_but_a_volume_falls_back_without_a_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Degrades to exactly the old drop-volume call: name + number.

    There is no year to build a range from, so no range is sent — and
    with nothing constraining the cover date there is nothing to guard
    against and no year to rank by. Every row comes back, which is what
    the old call returned.
    """
    issues = {
        ("Spider-Man", 1994, None): [
            _FakeBaseIssue(
                iid=510,
                number="1",
                series_name="Spider-Man",
                cover_year=1994,
                series_id=100,
                series_volume=9,
            )
        ],
    }
    fake = _VolumeAwareMokkari(issues_by_match=issues)
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(series="Spider-Man", issue="1", issue_int=1, volume=2)
    candidates = src.search(profile)

    assert [c.issue_id for c in candidates] == [510]
    assert len(fake.issues_list_calls) == 2
    wide = fake.issues_list_calls[1]
    assert wide == {"series_name": "Spider-Man", "number": "1"}


def test_no_volume_in_profile_still_widens_the_years(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without a volume there is still a year to widen, so the fallback runs."""
    fake = _VolumeAwareMokkari(issues_by_match={})
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(series="Foo", issue="1", issue_int=1, year=2020)  # no volume
    candidates = src.search(profile)

    assert candidates == []
    # No call ever included series_volume — there was none to send.
    assert all("series_volume" not in c for c in fake.issues_list_calls)
    # Two calls, where the old shape spent three.
    assert len(fake.issues_list_calls) == 2


def test_volume_match_does_not_trigger_the_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Year-exact + volume hits → the fallback never runs."""
    issues = {
        ("Spider-Man", 2020, 2): [
            _FakeBaseIssue(
                iid=600,
                number="1",
                series_name="Spider-Man",
                cover_year=2020,
                series_id=100,
            )
        ],
    }
    fake = _VolumeAwareMokkari(issues_by_match=issues)
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(
        series="Spider-Man", issue="1", issue_int=1, year=2020, volume=2
    )
    candidates = src.search(profile)

    assert [c.issue_id for c in candidates] == [600]
    # Only the first call ran — no widening of any kind.
    assert len(fake.issues_list_calls) == 1


def test_series_id_path_omits_volume_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--series-id trumps volume; the filter is skipped on that fast path."""
    issues = {
        (200, 2020, None): [
            _FakeBaseIssue(
                iid=700,
                number="1",
                series_name="Bypassed",
                cover_year=2020,
                series_id=200,
            )
        ],
    }
    fake = _VolumeAwareMokkari(issues_by_match=issues)
    src = _make_metron_source_with_series_id(monkeypatch, fake, series_id=200)
    profile = ComicProfile(
        series="Spider-Man", issue="1", issue_int=1, year=2020, volume=99
    )
    candidates = src.search(profile)

    assert [c.issue_id for c in candidates] == [700]
    assert len(fake.issues_list_calls) == 1
    assert "series_volume" not in fake.issues_list_calls[0]


# ---------------------------------------- wide fallback: guard + precedence


class _RangeIgnoringMokkari(_FakeMokkari):
    """
    An un-upgraded Metron: it drops filter params it does not recognize.

    DRF ignores unknown query params rather than rejecting them, so a
    server that predates the `cover_date_range_*` filters answers the
    wide call with the whole series instead of three years of it —
    silently, and with a 200.
    """

    def __init__(self, rows: list[_FakeBaseIssue]) -> None:
        super().__init__(issues_by_key={})
        self._rows = rows

    @override
    def issues_list(self, params: dict | None = None) -> list[_FakeBaseIssue]:
        params = dict(params or {})
        self.issues_list_calls.append(params)
        if params.get("cover_year") is not None:
            return []  # the exact call misses; the fallback follows
        return list(self._rows)


def test_rows_outside_the_range_are_dropped_and_warned_about(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A server ignoring the range must not widen the search silently."""
    from loguru import logger as loguru_logger

    from comicbox.formats.base.online import warn_once as warn_once_module

    monkeypatch.setattr(warn_once_module, "_seen", set())
    rows = [
        _FakeBaseIssue(
            iid=1987, number="1", series_name="Foo", cover_year=1987, series_id=100
        ),
        _FakeBaseIssue(
            iid=2019, number="1", series_name="Foo", cover_year=2019, series_id=100
        ),
    ]
    fake = _RangeIgnoringMokkari(rows=rows)
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(series="Foo", issue="1", issue_int=1, year=2020)

    messages: list[str] = []
    handler_id = loguru_logger.add(messages.append, level="WARNING", format="{message}")
    try:
        candidates = src.search(profile)
    finally:
        loguru_logger.remove(handler_id)

    # The 1987 row would have been ranked against a 2020 profile.
    assert [c.issue_id for c in candidates] == [2019]
    assert sum("cover-date range" in m for m in messages) == 1


def test_rows_inside_the_range_do_not_warn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guard is silent when the server honored the filter."""
    from loguru import logger as loguru_logger

    from comicbox.formats.base.online import warn_once as warn_once_module

    monkeypatch.setattr(warn_once_module, "_seen", set())
    rows = [
        _FakeBaseIssue(
            iid=2021, number="1", series_name="Foo", cover_year=2021, series_id=100
        ),
    ]
    fake = _RangeIgnoringMokkari(rows=rows)
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(series="Foo", issue="1", issue_int=1, year=2020)

    messages: list[str] = []
    handler_id = loguru_logger.add(messages.append, level="WARNING", format="{message}")
    try:
        candidates = src.search(profile)
    finally:
        loguru_logger.remove(handler_id)

    assert [c.issue_id for c in candidates] == [2021]
    assert not [m for m in messages if "cover-date range" in m]


def _wide_search_ids(
    monkeypatch: pytest.MonkeyPatch,
    rows: list[_FakeBaseIssue],
    *,
    volume: int | None = 2,
) -> list[int]:
    """Miss on the exact call, then run the fallback over `rows`."""
    fake = _RangeIgnoringMokkari(rows=rows)
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(
        series="Foo", issue="1", issue_int=1, year=2020, volume=volume
    )
    return [c.issue_id for c in src.search(profile)]


def _row(iid: int, *, year: int, volume: int) -> _FakeBaseIssue:
    return _FakeBaseIssue(
        iid=iid,
        number="1",
        series_name="Foo",
        cover_year=year,
        series_id=100,
        series_volume=volume,
    )


def test_precedence_prefers_the_profile_volume_at_the_exact_year(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Tier 1 of the old cascade: the call it would have stopped at.

    The six calls never ranked anything — they stopped at the first one
    that returned rows, so their ORDER was the ranking. Handing the
    matcher the whole three-year window instead would flip an
    adjacent-year reboot from a solo auto-write to a prompt, because the
    matcher has no volume signal of its own.
    """
    rows = [
        _row(1, year=2019, volume=2),
        _row(2, year=2020, volume=2),
        _row(3, year=2020, volume=5),
        _row(4, year=2021, volume=5),
    ]
    assert _wide_search_ids(monkeypatch, rows) == [2]


def test_precedence_falls_to_the_profile_volume_at_a_neighboring_year(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tier 2: the volume still matches, the cover date drifted."""
    rows = [
        _row(1, year=2019, volume=2),
        _row(3, year=2020, volume=5),
        _row(4, year=2021, volume=5),
    ]
    assert _wide_search_ids(monkeypatch, rows) == [1]


def test_precedence_falls_to_the_exact_year_at_any_volume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tier 3: the old drop-volume year-exact call."""
    rows = [
        _row(3, year=2020, volume=5),
        _row(4, year=2021, volume=5),
        _row(5, year=2020, volume=7),
    ]
    assert _wide_search_ids(monkeypatch, rows) == [3, 5]


def test_precedence_falls_to_any_volume_at_a_neighboring_year(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tier 4: the last pair of calls, whose results the old code merged."""
    rows = [
        _row(4, year=2021, volume=5),
        _row(6, year=2019, volume=7),
    ]
    assert _wide_search_ids(monkeypatch, rows) == [4, 6]


def test_precedence_without_a_profile_volume_is_exact_year_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no volume to match, the first two tiers are empty by definition."""
    rows = [
        _row(1, year=2019, volume=2),
        _row(3, year=2020, volume=5),
    ]
    assert _wide_search_ids(monkeypatch, rows, volume=None) == [3]


# ------------------------------------------------- volume-scoped lookup


def test_lookup_issue_in_volume_filters_by_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The warm path sends one `series_id` + `number` request."""
    issues = {300: [_FakeBaseIssue(iid=800, number="7", series_name="Blackhawk")]}
    fake = _FakeMokkari(issues_by_key=issues)
    src = _make_metron_source(monkeypatch, fake)
    candidate = src.lookup_issue(300, "007")

    assert candidate is not None
    assert candidate.issue_id == 800
    assert fake.issues_list_calls == [{"series_id": 300, "number": "7"}]


@pytest.mark.parametrize("issue_number", [None, "", "   "])
def test_lookup_issue_in_volume_without_number_makes_no_request(
    monkeypatch: pytest.MonkeyPatch, issue_number: str | None
) -> None:
    """
    No issue number → no request at all.

    A bare `issues_list({"series_id": N})` has no `number` filter, so
    mokkari pages through every issue in the series and the first row
    would be accepted as the match. Return None instead and let the
    caller fall back to the search path.
    """
    issues = {300: [_FakeBaseIssue(iid=800, number="7", series_name="Blackhawk")]}
    fake = _FakeMokkari(issues_by_key=issues)
    src = _make_metron_source(monkeypatch, fake)

    assert src.lookup_issue(300, issue_number) is None
    assert fake.issues_list_calls == []


def test_get_session_memoizes_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """The upstream client is built once per credential set, then reused."""
    from comicbox.formats.metron_api import online_source as metron_online_source

    # Isolate the process-wide per-credential session cache so this test
    # neither sees nor leaves behind entries for ("u", "p").
    monkeypatch.setattr(metron_online_source, "_session_cache", {})
    monkeypatch.setattr(metron_online_source, "_gate_cache", {})
    creds = OnlineSourceCredentials(user="u", password="p")
    settings = OnlineSettings()
    src = MetronOnlineSource(creds, settings)
    builds = {"n": 0}

    def fake_build(_gate=None):
        builds["n"] += 1
        return object()

    monkeypatch.setattr(src, "_build_session", fake_build)
    first = src._get_session()
    second = src._get_session()
    assert first is second
    assert builds["n"] == 1


# ---------------------------------------------------- retry classification


def _http_api_error(
    status: int, url: str, body: str = "<html>error</html>"
) -> ApiError:
    """
    Build the ApiError shape mokkari raises for an HTTP failure.

    mokkari chains the requests error (``raise ApiError(msg) from err``)
    and inlines ``repr(HTTPError)`` — full URL included — in the message,
    which is why the classifier reads the chained response's status
    rather than hunting for digits in the text.
    """
    response = Response()
    response.status_code = status
    cause = HTTPError(f"{status} Error for url: {url}", response=response)
    exc = ApiError(f"HTTP error: {cause!r} | Response body: {body}")
    exc.__cause__ = cause
    return exc


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        pytest.param(
            RateLimitError(
                "Rate limit exceeded: You have reached the 20 requests per "
                "minute limit. Please wait 30 seconds before making another "
                "request.",
                retry_after=0.0,
            ),
            RetryCategory.RATE_LIMIT,
            id="rate-limit-error",
        ),
        # mokkari's AuthenticationError takes no arguments; it bakes in its
        # own "Missing authorization information" message.
        pytest.param(
            AuthenticationError(),
            RetryCategory.AUTH,
            id="authentication-error",
        ),
        pytest.param(
            ApiError(
                "HTTP error: HTTPError('401 Client Error: Unauthorized for "
                "url: https://metron.cloud/api/issue/1/') | Response body: "
                '{"detail": "Invalid token."}'
            ),
            RetryCategory.AUTH,
            id="api-error-401",
        ),
        pytest.param(
            ApiError("Invalid username/password."),
            RetryCategory.AUTH,
            id="api-error-bad-credentials",
        ),
        # SPEC-BUG regression: a throttle body served as ApiError must
        # classify as RATE_LIMIT (rate-limit markers are checked FIRST),
        # not fall through to AUTH or TRANSIENT.
        pytest.param(
            ApiError("Rate limit exceeded for this api key. Expires in 42 seconds."),
            RetryCategory.RATE_LIMIT,
            id="api-error-throttle-body",
        ),
        pytest.param(
            ApiError("Connection error: ReadTimeout(ReadTimeoutError(...))"),
            RetryCategory.TRANSIENT,
            id="api-error-connection",
        ),
        # The chained response's status is authoritative, so a Metron id
        # that merely contains "401"/"403" can't strand a retriable 5xx as
        # a permanent auth failure.
        pytest.param(
            _http_api_error(502, "https://metron.cloud/api/issue/14031/"),
            RetryCategory.TRANSIENT,
            id="api-error-5xx-id-contains-401",
        ),
        pytest.param(
            _http_api_error(503, "https://metron.cloud/api/issue/?cv_id=44013"),
            RetryCategory.TRANSIENT,
            id="api-error-5xx-cv-id-contains-403",
        ),
        pytest.param(
            _http_api_error(401, "https://metron.cloud/api/issue/1/"),
            RetryCategory.AUTH,
            id="api-error-chained-401",
        ),
        pytest.param(
            _http_api_error(403, "https://metron.cloud/api/issue/1/"),
            RetryCategory.AUTH,
            id="api-error-chained-403",
        ),
        # A throttle served with a non-429 status still retries: the
        # wording is checked before the status.
        pytest.param(
            _http_api_error(
                403, "https://metron.cloud/api/issue/1/", body="Request was throttled."
            ),
            RetryCategory.RATE_LIMIT,
            id="api-error-cdn-throttle-403",
        ),
        # Pins that the old bare-"auth" marker is gone: an ApiError carrying
        # a pydantic dump with a creator-ish "authors" field must not
        # substring-match into AUTH.
        pytest.param(
            ApiError(
                "Validation error: {'name': 'Watchmen #5', 'authors': ['Alan Moore']}"
            ),
            RetryCategory.TRANSIENT,
            id="api-error-authors-field-not-auth",
        ),
        # A cache object missing get()/store() is a wiring bug; replaying
        # the request can only fail the same way.
        pytest.param(
            CacheError(
                "Cache object passed in is missing attribute: AttributeError('get')"
            ),
            RetryCategory.INVALID,
            id="cache-error-invalid",
        ),
        # Not a mokkari exception — the classifier declines and the retry
        # decorator's conservative fallback takes over.
        pytest.param(
            LookupError("metron: issue 5 not found"),
            None,
            id="non-mokkari-declined",
        ),
    ],
)
def test_classify_retry_exception(
    exc: BaseException, expected: RetryCategory | None
) -> None:
    assert MetronOnlineSource.classify_retry_exception(exc) is expected


@pytest.mark.parametrize(
    "exc",
    [
        # A cache object missing get()/store() is a wiring bug: mokkari
        # raises this on the first request, not in Session.__init__, so it
        # lands inside the retry loop.
        CacheError("Cache object passed in is missing attribute: get"),
        # Missing local credentials; replaying cannot conjure them.
        AuthenticationError(),
        # Metron rejected the request itself.
        _http_api_error(401, "https://metron.cloud/api/issue/1/"),
    ],
    ids=["cache-error", "auth-error", "http-401"],
)
def test_terminal_failures_are_called_exactly_once(exc: BaseException) -> None:
    """A terminal classification must not be replayed by the retry loop."""
    calls = {"n": 0}

    class _Source:
        classify_retry_exception = staticmethod(
            MetronOnlineSource.classify_retry_exception
        )

        @with_retry()
        def call(self) -> None:
            calls["n"] += 1
            raise exc

    with pytest.raises(type(exc)):
        _Source().call()
    assert calls["n"] == 1


def test_with_retry_replays_api_error_throttle_body() -> None:
    """
    End-to-end SPEC-BUG regression through the decorator.

    A throttle response surfaced as `ApiError` (no `retry_after` hint)
    must be classified RATE_LIMIT, sleep the rate-limit schedule's first
    delay, and replay the call — not raise or use the generic schedule.
    """
    sleeps: list[float] = []
    calls = {"n": 0}

    class _Stub:
        classify_retry_exception = staticmethod(
            MetronOnlineSource.classify_retry_exception
        )
        on_rate_limit = None
        retry_sleep = None
        name = "metron"

        @with_retry(sleep=sleeps.append)
        def fetch(self) -> str:
            calls["n"] += 1
            if calls["n"] == 1:
                msg = "Rate limit exceeded for this api key."
                raise ApiError(msg)
            return "ok"

    assert _Stub().fetch() == "ok"
    # The call was replayed: the throttled attempt + the successful one.
    assert calls["n"] == 2
    # No retry_after hint on ApiError, so the rate-limit schedule applies.
    assert sleeps == [_RATE_LIMIT_SCHEDULE[0]]
