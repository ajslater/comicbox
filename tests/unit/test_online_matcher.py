"""Online matcher tests: signals, scoring, policy resolution."""

from __future__ import annotations

import pytest

from comicbox.config.settings import OnlineSettings, Policy
from comicbox.online.matcher import (
    OnlineMatcher,
    ResolutionKind,
    metadata_score,
)
from comicbox.online.profile import (
    Candidate,
    CandidateSummary,
    ComicProfile,
    parse_issue_int,
    parse_year,
    strip_issue_leading_zeros,
)
from comicbox.online.signals import (
    s_issue,
    s_pages,
    s_publisher,
    s_series,
    s_year,
)


def _candidate(
    *,
    issue_id: int = 1,
    series: str = "Foo Comics",
    issue: str = "5",
    year: int | None = 2020,
    publisher: str | None = "Quality Comics",
    page_count: int | None = 24,
) -> Candidate:
    return Candidate(
        source="metron",
        issue_id=issue_id,
        summary=CandidateSummary(
            series=series,
            issue=issue,
            year=year,
            publisher=publisher,
            page_count=page_count,
            cover_url=None,
            variant_label=None,
        ),
    )


def _profile(**overrides) -> ComicProfile:
    base = {
        "series": "Foo Comics",
        "issue": "5",
        "issue_int": 5,
        "year": 2020,
        "publisher": "Quality Comics",
        "page_count": 24,
    }
    base.update(overrides)
    return ComicProfile(**base)


# --------------------------------------------------------- helpers


def test_parse_issue_int_strips_leading_zeros() -> None:
    assert parse_issue_int("001") == 1
    assert parse_issue_int("01") == 1
    assert parse_issue_int("5") == 5


def test_parse_issue_int_returns_none_for_non_numeric() -> None:
    assert parse_issue_int("1a") is None
    assert parse_issue_int("1.5") is None
    assert parse_issue_int("Special") is None
    assert parse_issue_int("") is None
    assert parse_issue_int(None) is None


def test_parse_year_extracts_4_digit() -> None:
    assert parse_year("2020-04-01") == 2020
    assert parse_year(2020) == 2020
    assert parse_year("Spring 2020") == 2020
    assert parse_year("no year here") is None
    assert parse_year(None) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("007", "7"),
        ("01", "1"),
        ("1", "1"),
        ("0", "0"),
        ("000", "0"),
        ("001a", "1a"),
        ("0a", "0a"),
        ("1.5", "1.5"),
        ("1/2", "1/2"),
        ("Special", "Special"),
        ("", ""),
        (None, None),
    ],
)
def test_strip_issue_leading_zeros(raw: str | None, expected: str | None) -> None:
    assert strip_issue_leading_zeros(raw) == expected


# --------------------------------------------------------- signals


class TestSeriesSignal:
    def test_exact_match_is_one(self) -> None:
        assert s_series(_profile(), _candidate()) == 1.0

    def test_volume_suffix_normalized(self) -> None:
        score = s_series(
            _profile(series="Foo Comics"),
            _candidate(series="Foo Comics (Vol. 2)"),
        )
        assert score >= 0.8

    def test_punctuation_normalized(self) -> None:
        score = s_series(
            _profile(series="X-Men"),
            _candidate(series="X Men"),
        )
        assert score >= 0.8

    def test_missing_either_side_zero(self) -> None:
        assert s_series(_profile(series=None), _candidate()) == 0.0
        assert s_series(_profile(), _candidate(series="")) == 0.0


class TestIssueSignal:
    def test_int_match_is_one(self) -> None:
        assert s_issue(_profile(issue_int=5), _candidate(issue="5")) == 1.0
        assert s_issue(_profile(issue_int=5), _candidate(issue="005")) == 1.0

    def test_int_mismatch_is_zero(self) -> None:
        assert s_issue(_profile(issue_int=5), _candidate(issue="6")) == 0.0

    def test_string_match_is_one(self) -> None:
        assert (
            s_issue(_profile(issue_int=None, issue="1a"), _candidate(issue="1a")) == 1.0
        )

    def test_missing_one_side_returns_partial_credit(self) -> None:
        score = s_issue(_profile(issue=None, issue_int=None), _candidate(issue="5"))
        assert score == 0.5


class TestYearSignal:
    def test_exact_year_one(self) -> None:
        assert s_year(_profile(year=2020), _candidate(year=2020)) == 1.0

    def test_off_by_one(self) -> None:
        assert s_year(_profile(year=2020), _candidate(year=2021)) == 0.7

    def test_off_by_two(self) -> None:
        assert s_year(_profile(year=2020), _candidate(year=2022)) == 0.4

    def test_far_off_zero(self) -> None:
        assert s_year(_profile(year=2020), _candidate(year=2010)) == 0.0

    def test_missing_partial_credit(self) -> None:
        assert s_year(_profile(year=None), _candidate(year=2020)) == 0.6
        assert s_year(_profile(), _candidate(year=None)) == 0.6


class TestPublisherSignal:
    def test_exact(self) -> None:
        assert (
            s_publisher(
                _profile(publisher="Quality Comics"),
                _candidate(publisher="Quality Comics"),
            )
            == 1.0
        )

    def test_normalized_match(self) -> None:
        assert (
            s_publisher(
                _profile(publisher="Quality Comics, Inc."),
                _candidate(publisher="quality"),
            )
            == 1.0
        )

    def test_different(self) -> None:
        assert (
            s_publisher(
                _profile(publisher="DC"),
                _candidate(publisher="Marvel"),
            )
            == 0.0
        )

    def test_missing(self) -> None:
        assert s_publisher(_profile(publisher=None), _candidate()) == 0.5


class TestPagesSignal:
    def test_exact(self) -> None:
        assert s_pages(_profile(page_count=24), _candidate(page_count=24)) == 1.0

    def test_within_10pct(self) -> None:
        assert s_pages(_profile(page_count=24), _candidate(page_count=22)) == 0.7

    def test_within_25pct(self) -> None:
        assert s_pages(_profile(page_count=24), _candidate(page_count=20)) == 0.3

    def test_far_off(self) -> None:
        assert s_pages(_profile(page_count=24), _candidate(page_count=48)) == 0.0


# --------------------------------------------------------- scoring


def test_perfect_match_scores_one() -> None:
    score = metadata_score(_profile(), _candidate())
    assert score == pytest.approx(1.0)


def test_wrong_issue_drops_score() -> None:
    score = metadata_score(_profile(issue_int=5), _candidate(issue="6"))
    # Issue weight is 0.25 / 0.80 = ~0.3125; missing it should drop to ~0.6875.
    assert 0.65 < score < 0.72


def test_partial_match_above_min_confidence() -> None:
    # Right series + issue, missing publisher + pages, year off by one.
    score = metadata_score(
        _profile(publisher=None, page_count=None, year=2020),
        _candidate(publisher=None, page_count=None, year=2021),
    )
    assert score >= 0.50


# --------------------------------------------------------- resolution


def _settings(**overrides) -> OnlineSettings:
    return OnlineSettings(
        confidence_threshold=overrides.pop("confidence_threshold", 0.85),
        **overrides,
    )


# Default policy is `normal`, default unattended is False.
def test_auto_write_when_top_clears_threshold_with_gap() -> None:
    matcher = OnlineMatcher()
    ranked = [
        _candidate(issue_id=1),  # perfect match
        _candidate(issue_id=2, year=2010),  # far off year
    ]
    ranked = matcher.rank(_profile(), ranked)
    res = matcher.resolve(ranked, _settings(), source_name="metron")
    assert res.kind is ResolutionKind.AUTO_WRITE
    assert res.chosen is not None
    assert res.chosen.issue_id == 1


def test_no_match_when_all_below_min_confidence() -> None:
    matcher = OnlineMatcher()
    # All candidates are wildly wrong.
    bad = [_candidate(series="Totally Different Series", issue="999", year=1900)]
    ranked = matcher.rank(_profile(), bad)
    res = matcher.resolve(ranked, _settings(), source_name="metron")
    assert res.kind is ResolutionKind.NO_MATCH


def test_prompt_when_close_call_default_policy() -> None:
    matcher = OnlineMatcher()
    # Both candidates clear min_confidence with similar scores.
    candidates = [
        _candidate(issue_id=1),
        _candidate(issue_id=2, page_count=22),  # tiny ding
    ]
    ranked = matcher.rank(_profile(), candidates)
    res = matcher.resolve(
        ranked, _settings(confidence_threshold=0.99), source_name="metron"
    )
    assert res.kind is ResolutionKind.PROMPT


def test_strict_unattended_skips_when_close() -> None:
    """`--unattended --policy strict` skips ambiguous → SKIP."""
    matcher = OnlineMatcher()
    candidates = [
        _candidate(issue_id=1),
        _candidate(issue_id=2, page_count=22),
    ]
    ranked = matcher.rank(_profile(), candidates)
    res = matcher.resolve(
        ranked,
        _settings(confidence_threshold=0.99, policy=Policy.STRICT, unattended=True),
        source_name="metron",
    )
    assert res.kind is ResolutionKind.SKIP


def test_normal_accepts_solo_below_threshold() -> None:
    """`--policy normal` (default) takes a sole viable candidate even below auto-write bar."""
    matcher = OnlineMatcher()
    candidates = [
        _candidate(issue_id=1, page_count=22),  # 0.7 weight on pages
    ]
    ranked = matcher.rank(_profile(), candidates)
    res = matcher.resolve(
        ranked, _settings(confidence_threshold=0.99), source_name="metron"
    )
    assert res.kind is ResolutionKind.AUTO_WRITE
    assert res.chosen is not None
    assert res.chosen.issue_id == 1


def test_strict_prompts_solo_below_threshold() -> None:
    """`--policy strict` requires unambig — solo viable below threshold prompts."""
    matcher = OnlineMatcher()
    candidates = [_candidate(issue_id=1, page_count=22)]
    ranked = matcher.rank(_profile(), candidates)
    res = matcher.resolve(
        ranked,
        _settings(confidence_threshold=0.99, policy=Policy.STRICT),
        source_name="metron",
    )
    assert res.kind is ResolutionKind.PROMPT


def test_eager_waives_gap_rule() -> None:
    """`--policy eager` auto-writes top above threshold even with narrow gap."""
    matcher = OnlineMatcher()
    candidates = [
        _candidate(issue_id=1),
        _candidate(issue_id=2, page_count=22),  # similar score
    ]
    ranked = matcher.rank(_profile(), candidates)
    # Pick a threshold that the top clears but the runner-up nearly does too.
    res = matcher.resolve(
        ranked,
        _settings(confidence_threshold=0.50, policy=Policy.EAGER),
        source_name="metron",
    )
    assert res.kind is ResolutionKind.AUTO_WRITE


def test_always_prompt_never_auto_writes() -> None:
    """`always-prompt` defers every viable case to the user."""
    matcher = OnlineMatcher()
    ranked = [
        _candidate(issue_id=1),  # perfect match
        _candidate(issue_id=2, year=2010),
    ]
    ranked = matcher.rank(_profile(), ranked)
    res = matcher.resolve(
        ranked, _settings(policy=Policy.ALWAYS_PROMPT), source_name="metron"
    )
    assert res.kind is ResolutionKind.PROMPT


def test_per_source_policy_override() -> None:
    """`policy_per_source['comicvine'] = strict` overrides the global policy."""
    matcher = OnlineMatcher()
    candidates = [_candidate(issue_id=1, page_count=22)]
    ranked = matcher.rank(_profile(), candidates)
    settings = _settings(
        confidence_threshold=0.99,
        policy=Policy.NORMAL,
        policy_per_source={"comicvine": Policy.STRICT},
    )
    # Metron uses global = normal → AUTO_WRITE solo.
    res_metron = matcher.resolve(ranked, settings, source_name="metron")
    assert res_metron.kind is ResolutionKind.AUTO_WRITE
    # ComicVine uses override = strict → PROMPT.
    res_cv = matcher.resolve(ranked, settings, source_name="comicvine")
    assert res_cv.kind is ResolutionKind.PROMPT


def test_per_source_confidence_threshold_override() -> None:
    """`confidence_threshold_per_source` lets one source use a different bar."""
    matcher = OnlineMatcher()
    # Two candidates, both viable, top ~0.875 with small gap (year way off
    # docks ~0.125; page_count off docks a small extra). `eager` policy
    # depends only on threshold — neither solo_viable nor unambig fire here,
    # so the per-source threshold is the deciding knob.
    candidates = [
        _candidate(issue_id=1, year=2010),
        _candidate(issue_id=2, year=2010, page_count=22),
    ]
    ranked = matcher.rank(_profile(), candidates)
    settings = _settings(
        confidence_threshold=0.99,
        confidence_threshold_per_source={"metron": 0.50},
        policy=Policy.EAGER,
    )
    res_metron = matcher.resolve(ranked, settings, source_name="metron")
    assert res_metron.kind is ResolutionKind.AUTO_WRITE
    res_cv = matcher.resolve(ranked, settings, source_name="comicvine")
    assert res_cv.kind is ResolutionKind.PROMPT
