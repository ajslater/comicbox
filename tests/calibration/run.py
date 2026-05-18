"""
Calibration harness for the online-tagging matcher.

Reads `fixtures.json` (gitignored, per-developer), runs the configured
online sources against each fixture's comic file, and reports how well
the top-ranked candidate matches the fixture's expected id — bucketed
by score band.

This is a **live API** harness: it hits Metron and ComicVine. Both
libraries enforce per-IP rate limits via SQLite-backed buckets that
persist across runs (Metron: 20/min and 5,000/day, ComicVine: 1/sec
and 200/hour). The cache also persists, so the second run on the same
fixture set is near-instant.

Usage:

    # First, copy fixtures.example.json → fixtures.json and populate
    # with (file_path, expected_metron_id, expected_comicvine_id) entries.
    # Credentials must be configured (env vars or ~/.config/comicbox/config.yaml).

    uv run python -m tests.calibration.run

    # Or limit to one source:
    uv run python -m tests.calibration.run --sources metron

    # Or use a specific fixture file:
    uv run python -m tests.calibration.run --fixtures path/to/fixtures.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
import traceback
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Protocol, Self

from comicbox.box import Comicbox
from comicbox.config import get_config
from comicbox.formats.base.online.matcher import OnlineMatcher
from comicbox.formats.comicvine_api.online_source import ComicVineOnlineSource
from comicbox.formats.metron_api.online_source import MetronOnlineSource

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from comicbox.config.settings import OnlineSettings
    from comicbox.formats.base.online.matcher import (
        CandidateHashFetcher,
        LocalHashProvider,
    )
    from comicbox.formats.base.online.profile import Candidate
    from comicbox.formats.base.online.sources.base import OnlineSource


# Score bands for the report. Inclusive lower bound, exclusive upper.
_SCORE_BANDS: tuple[tuple[float, float, str], ...] = (
    (0.95, 1.001, "0.95-1.00 (very high)"),
    (0.85, 0.95, "0.85-0.95 (auto-write)"),
    (0.70, 0.85, "0.70-0.85 (prompt zone)"),
    (0.50, 0.70, "0.50-0.70 (solo-viable)"),
    (0.0, 0.50, "0.00-0.50 (below min_confidence)"),
)


@dataclass(frozen=True, slots=True)
class _Fixture:
    file_path: Path
    expected: dict[str, int]  # source_name → expected issue id
    cover_quality: str  # "full" | "thumbnail" | "missing"


@dataclass(frozen=True, slots=True)
class _CandidateSummary:
    """Per-candidate breakdown for MISS-case diagnostic output."""

    issue_id: int
    score: float  # blended (metadata + cover when hashing fired)
    metadata_score: float
    cover_score: float | None  # None when this candidate didn't get hashed
    # Volume/series name as the source returned it. Useful for "which
    # reprint did this come from" forensics when ids alone are opaque:
    # CV issue id 476696 means nothing visually, but "Watchmen Annotated"
    # tells you immediately what you're looking at.
    series: str = ""
    summary_year: int | None = (
        None  # the issue's cover_date.year as the source returned it
    )
    # The parent container id from the source (CV's volume.id /
    # Metron's series.id). Lets a calibration reader distinguish two
    # candidates with the same series name from same-volume variant
    # records vs different-volume name collisions.
    volume_id: int | None = None


# How many top candidates to retain on each outcome for MISS diagnostics.
# Three is enough to see "right answer is at rank 2 or 3" patterns without
# making the saved outcomes JSON enormous.
_TOP_K_FOR_DIAGNOSTIC: int = 3


@dataclass(slots=True)
class _Outcome:
    """One (fixture, source) pair's calibration outcome."""

    fixture: _Fixture
    source_name: str
    top_score: float
    top_issue_id: int | None
    top_correct: bool | None  # None = no candidates
    n_candidates: int
    error: str | None = None  # set when search fails
    # Diagnostic detail for the top candidate. Set when ranking produced
    # at least one candidate; left at defaults when search errored or
    # returned nothing. Used by `_print_failed_outcomes` to surface
    # whether cover hashing fired and how it scored against the metadata
    # signal.
    top_metadata_score: float | None = None
    top_cover_score: float | None = None  # None when hashing didn't fire or failed
    runner_up_score: float | None = None  # None when there's only one candidate
    hash_providers_supplied: bool = False  # False when cover_quality != "full"
    # Top-K candidate breakdowns retained for MISS-case investigation.
    # When the top candidate is tied or near-tied with the runner-up,
    # the runner-up's score breakdown tells us whether the right answer
    # is sitting at rank 2 (lost the tiebreak) or genuinely below
    # everyone. Empty when there were no candidates.
    top_candidates: list[_CandidateSummary] = field(default_factory=list)
    # Per-method API-call counts observed for THIS fixture only. The
    # harness snapshots the source's `api_call_counts` before and after
    # `_score_one` and stores the diff. Includes cache hits (we can't
    # distinguish those without peeking inside simyan/mokkari) so the
    # number is an upper bound on actual rate-limit budget consumed —
    # exact for cold-cache runs, over-counts for warm-cache.
    api_call_counts: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class _SourceReport:
    correct: int = 0
    wrong: int = 0
    no_candidates: int = 0
    errored: int = 0
    no_expected_id: int = 0  # fixture didn't list this source
    by_band: dict[str, dict[str, int]] = field(default_factory=dict)


# Outcome tags written to outcomes.json — also what `--retry-misses` looks for.
_MISS_TAGS: frozenset[str] = frozenset({"wrong", "no_candidates", "error"})


def _classify_outcome(o: _Outcome) -> str:
    """Map an _Outcome to a short tag for serialization / retry-misses filtering."""
    if o.error:
        return "error"
    if o.n_candidates == 0:
        return "no_candidates"
    if o.top_correct is None:
        return "no_expected_id"
    return "correct" if o.top_correct else "wrong"


def _outcome_to_dict(o: _Outcome) -> dict:
    """Serialize one _Outcome to its JSON-dict shape."""
    return {
        "file": str(o.fixture.file_path),
        "source": o.source_name,
        "outcome": _classify_outcome(o),
        "top_score": o.top_score,
        "top_issue_id": o.top_issue_id,
        "expected": o.fixture.expected.get(o.source_name),
        "n_candidates": o.n_candidates,
        "error": o.error,
        # Diagnostic fields — useful for post-hoc analysis of which
        # cases hashing helped vs. where it didn't fire. Keys stay
        # present even when None so consumers see consistent shape.
        "top_metadata_score": o.top_metadata_score,
        "top_cover_score": o.top_cover_score,
        "runner_up_score": o.runner_up_score,
        "hash_providers_supplied": o.hash_providers_supplied,
        # Top-K candidate breakdowns. Empty list for no-candidate /
        # errored outcomes. Useful for "right answer at rank 2"
        # forensics on tied scores.
        "top_candidates": [
            {
                "issue_id": c.issue_id,
                "score": c.score,
                "metadata_score": c.metadata_score,
                "cover_score": c.cover_score,
                "series": c.series,
                "summary_year": c.summary_year,
                "volume_id": c.volume_id,
            }
            for c in o.top_candidates
        ],
        # Per-method API-call counts for this fixture's search + rank.
        # Includes cache hits — upper bound on rate-limit budget used.
        # Useful for Phase B comparison runs to measure how much the
        # api_budget knob saved against `balanced`.
        "api_call_counts": dict(o.api_call_counts),
    }


def _atomic_write_json(path: Path, payload: object) -> None:
    """
    Write JSON to `path` atomically: temp file + rename.

    Used by both the end-of-run save and the periodic checkpointer. The
    rename is atomic on POSIX (same-directory `Path.replace()`), so a
    `Ctrl-C` mid-write either leaves the original file untouched (if
    the temp was still being written) or completes the new file (if
    rename was reached). Never a half-written outcomes file.
    """
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n")
    tmp.replace(path)


def _serialize_outcomes(outcomes: list[_Outcome], path: Path) -> None:
    """Write outcomes to JSON for `--retry-misses` and post-hoc analysis."""
    _atomic_write_json(path, [_outcome_to_dict(o) for o in outcomes])


def _merge_outcomes_to_partial(path: Path, new_outcomes: list[_Outcome]) -> None:
    """
    Overlay new outcomes onto an existing partial file, preserving others.

    Used by filtered runs (`--retry-misses`, `--filter`, `--one-per-series`,
    `--limit`) so iterating a subset of failures doesn't wipe state for
    the fixtures we didn't retry. Keying is by (file, source):

    - Existing entries with a matching (file, source) → replaced by the
      new outcome (most recent result wins).
    - Existing entries without a match → preserved verbatim.
    - New (file, source) not present in the file → appended (handles
      "user added a fixture between runs").

    When the file doesn't exist, falls back to a plain write — the
    first filtered run after a clean slate has nothing to merge into.

    Without this, each `--retry-misses` overwrites the whole partial
    with just the subset it ran: passing 1 fixture into Watchmen-only
    retry deletes the other 14 fixtures' last-known states, and the
    next `--retry-misses` sees an empty miss set even though those
    fixtures are still actually broken.
    """
    if not path.exists():
        _serialize_outcomes(new_outcomes, path)
        return

    new_by_key: dict[tuple[str, str], dict] = {
        (str(o.fixture.file_path), o.source_name): _outcome_to_dict(o)
        for o in new_outcomes
    }
    overlaid: set[tuple[str, str]] = set()

    existing = json.loads(path.read_text())
    merged: list[dict] = []
    for entry in existing:
        key = (str(entry.get("file", "")), str(entry.get("source", "")))
        if key in new_by_key:
            merged.append(new_by_key[key])
            overlaid.add(key)
        else:
            merged.append(entry)

    # New (file, source) pairs not in the existing file — appended.
    # Preserves the existing file's order; new entries come last.
    for key, dict_entry in new_by_key.items():
        if key not in overlaid:
            merged.append(dict_entry)

    _atomic_write_json(path, merged)


def _load_miss_files(outcomes_path: Path) -> set[str]:
    """
    From a previous run's outcomes.json, return file paths that had any miss.

    A "miss" is wrong / no_candidates / error on at least one source. Comics
    where every queried source was correct (or no_expected_id) are dropped
    — we don't need to re-burn API budget on them.
    """
    raw = json.loads(outcomes_path.read_text())
    miss_files: set[str] = set()
    for entry in raw:
        if entry.get("outcome") in _MISS_TAGS:
            miss_files.add(str(entry["file"]))
    return miss_files


def _filter_to_misses(fixtures: list[_Fixture], miss_files: set[str]) -> list[_Fixture]:
    return [f for f in fixtures if str(f.file_path) in miss_files]


# "Series key" for --one-per-series: the part of the filename before the
# issue-number marker. Keeps the year-in-parens because that often
# distinguishes volumes ("Lois Lane (1986)" vs "Lois Lane (2019)").
# Examples:
#   "Watchmen (1986) #002.cbz"  → "Watchmen (1986)"
#   "Conan (2004) #005.cbz"     → "Conan (2004)"
#   "Lois Lane (2019) #001.cbz" → "Lois Lane (2019)"
#   "Akira (1984) #001.cbz"     → "Akira (1984)"  # same logical series
#                                                 # but treated as distinct
#                                                 # — conservative; user can
#                                                 # group further via --filter.
_ISSUE_MARKER_RE = re.compile(r"\s*#\d")


def _series_key(filename: str) -> str:
    """Reduce a comic filename to a stable key for --one-per-series."""
    return _ISSUE_MARKER_RE.split(filename, maxsplit=1)[0].rstrip()


def _dedupe_one_per_series(fixtures: list[_Fixture]) -> list[_Fixture]:
    """Keep only the first fixture for each series-key prefix."""
    seen: set[str] = set()
    out: list[_Fixture] = []
    for f in fixtures:
        key = _series_key(f.file_path.name)
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def _load_fixtures(path: Path) -> list[_Fixture]:
    """Parse fixtures.json into typed entries."""
    raw = json.loads(path.read_text())
    if not isinstance(raw, list):
        msg = f"{path}: expected a JSON list of fixtures"
        raise TypeError(msg)
    fixtures: list[_Fixture] = []
    for entry in raw:
        if not isinstance(entry, dict):
            msg = f"fixture entry is not a dict: {entry!r}"
            raise TypeError(msg)
        file_path = Path(str(entry["file"])).expanduser()
        expected: dict[str, int] = {}
        for source in ("metron", "comicvine"):
            value = entry.get(source)
            if value is not None:
                expected[source] = int(value)
        fixtures.append(
            _Fixture(
                file_path=file_path,
                expected=expected,
                cover_quality=entry.get("cover_quality", "full"),
            )
        )
    return fixtures


def _band_for(score: float) -> str:
    for low, high, label in _SCORE_BANDS:
        if low <= score < high:
            return label
    return "0.00-0.50 (below min_confidence)"


def _build_source(name: str, online: OnlineSettings) -> OnlineSource:
    creds = online.sources.get(name)
    if creds is None:
        msg = f"no credentials for source {name!r}"
        raise RuntimeError(msg)
    factory = {
        "metron": MetronOnlineSource,
        "comicvine": ComicVineOnlineSource,
    }[name]
    src: OnlineSource = factory(creds, online)
    if not src.is_configured():
        msg = (
            f"source {name!r} is not configured (missing credentials). "
            f"Set them via env vars or ~/.config/comicbox/config.yaml."
        )
        raise RuntimeError(msg)
    return src


class _HashProviderBox(Protocol):
    """
    Just-enough Comicbox surface for `_hash_providers` to bind callables.

    Spelling it as a Protocol (instead of `Comicbox`) lets unit tests pass
    a minimal duck without `cast(...)` shenanigans — and documents which
    bits of the box `_hash_providers` actually touches.
    """

    def _local_cover_phash(self) -> str | None: ...

    def _candidate_cover_hash_fetcher(self, url: str) -> str | None: ...


def _hash_providers(
    cb: _HashProviderBox, fixture: _Fixture
) -> tuple[LocalHashProvider | None, CandidateHashFetcher | None]:
    """
    Return the cover-hash providers the matcher should use for this fixture.

    Cover hashing only fires when the metadata-only top is ambiguous
    (matcher's `_should_invoke_hashing`), so passing the providers for
    every fixture is cheap — the lambda's only invoked when it matters.

    We gate on `cover_quality`:

    - **full** — pass both providers. `_local_cover_phash` reads the
      first archive page and hashes it; `_candidate_cover_hash_fetcher`
      downloads ComicVine cover URLs (Metron candidates ship a
      precomputed hash) into the shared SQLite cache. This is the
      production hashing path, just driven from the harness.
    - **thumbnail** / **missing** — return (None, None). Slimlib's
      shrunk covers and missing-cover fixtures produce noise at best
      and degrade the metadata-only signal at worst. We'd rather see
      the metadata-only number for these so we know what the matcher's
      doing without the hash boost.
    """
    if fixture.cover_quality != "full":
        return None, None
    # Bind to the instance methods (mixin-provided on Comicbox).
    return cb._local_cover_phash, cb._candidate_cover_hash_fetcher


def _format_duration(seconds: float) -> str:
    """Compact human-readable duration: '47s', '12m', '3.4h', '1.2d'."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}m"
    if seconds < 86400:
        return f"{seconds / 3600:.1f}h"
    return f"{seconds / 86400:.1f}d"


class _ETA:
    """
    Running estimate of when the calibration will finish.

    Tracks per-fixture wall-clock durations in a rolling window (last 20
    by default), then projects the average onto the remaining count. The
    rolling window — rather than overall average — keeps the ETA
    responsive to cache-warming (early fixtures slow, later fast) and to
    rate-limit walls (sudden multi-minute waits dominate the new
    average within a few fixtures).

    Wall-clock includes everything: API calls, rate-limit waits, cover
    downloads, and the local Comicbox open. That's what the user
    actually wants to plan around.
    """

    # Fixtures sampled for the rolling average. Small enough to react to
    # regime changes within a few fixtures; large enough to smooth out
    # single-fixture spikes.
    _ROLLING_WINDOW: ClassVar[int] = 20

    def __init__(self, total_fixtures: int) -> None:
        self._total = total_fixtures
        self._completed = 0
        self._start = time.monotonic()
        self._recent_durations: deque[float] = deque(maxlen=self._ROLLING_WINDOW)
        self._last_fixture_start: float | None = None

    def fixture_started(self) -> None:
        """Mark the moment a fixture begins. Called before `_score_one`."""
        self._last_fixture_start = time.monotonic()

    def fixture_finished(self) -> None:
        """Record this fixture's duration. Called after all sources scored."""
        if self._last_fixture_start is None:
            return
        self._recent_durations.append(time.monotonic() - self._last_fixture_start)
        self._completed += 1

    def remaining(self) -> int:
        return self._total - self._completed

    def elapsed_seconds(self) -> float:
        return time.monotonic() - self._start

    def eta_seconds(self) -> float | None:
        """Projected wall-clock to completion. None until any fixture finishes."""
        if not self._recent_durations or self.remaining() <= 0:
            return None
        avg = sum(self._recent_durations) / len(self._recent_durations)
        return avg * self.remaining()

    def progress_line(self) -> str:
        """Compact one-line summary suitable for heartbeat / periodic display."""
        elapsed_str = _format_duration(self.elapsed_seconds())
        eta = self.eta_seconds()
        eta_str = _format_duration(eta) if eta is not None else "—"
        return (
            f"overall {self._completed}/{self._total} fixtures, "
            f"{elapsed_str} elapsed, ETA {eta_str}"
        )


class _Heartbeat:
    """
    Background thread that prints a "still working" hint at intervals.

    The pyrate_limiter buckets in mokkari/simyan can park a single API
    call for up to an hour when an hourly cap is hit. Without this hint,
    the user sees a stalled-looking line and has no idea whether the
    process is wedged or just being polite.

    When an `_ETA` is passed, each tick also prints the overall progress
    line so the user can see both "current fixture stuck for 90s" AND
    "overall: 5/343 done, ETA 14h" — same heartbeat moment, two scales.
    """

    def __init__(
        self,
        label: str,
        *,
        interval: float = 15.0,
        eta: _ETA | None = None,
    ) -> None:
        self._label = label
        self._interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._start = time.monotonic()
        self._eta = eta

    def __enter__(self) -> Self:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._thread.join(timeout=self._interval + 1.0)

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            elapsed = time.monotonic() - self._start
            line = f"\n      [..still working on {self._label}, {elapsed:.0f}s elapsed]"
            if self._eta is not None:
                line += f"\n      [..{self._eta.progress_line()}]"
            print(line, flush=True)  # noqa: T201


def _diff_counts(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    """Per-method delta between two snapshots of `api_call_counts`."""
    return {
        method: after.get(method, 0) - before.get(method, 0)
        for method in set(before) | set(after)
        if after.get(method, 0) - before.get(method, 0) > 0
    }


def _score_one(
    source: OnlineSource,
    fixture: _Fixture,
) -> _Outcome:
    """
    Run search + rank on a fixture; produce an outcome.

    The Comicbox stays open for the full search+rank because the
    matcher may call back into it for the local cover pHash when
    metadata-only ranking is ambiguous (close call or below
    threshold). For `cover_quality != "full"` fixtures the providers
    are None and the matcher stays metadata-only — same as before.

    Captures the top candidate's metadata / cover sub-scores and the
    runner-up's blended score so `_print_failed_outcomes` can show
    whether hashing fired and how tight the call was.
    """
    hash_providers_supplied = False
    # Snapshot the source's API-call counters so we can compute the
    # per-fixture delta. The source's `api_call_counts` dict
    # accumulates over the whole run; we want only the slice for THIS
    # fixture's search + rank.
    counts_before = dict(source.api_call_counts)
    try:
        with Comicbox(fixture.file_path) as cb:
            cb.get_merged_metadata()
            profile = cb._build_profile()
            candidates: list[Candidate] = source.search(profile)
            local_provider, candidate_fetcher = _hash_providers(cb, fixture)
            hash_providers_supplied = local_provider is not None
            ranked = OnlineMatcher().rank(
                profile,
                candidates,
                local_hash_provider=local_provider,
                candidate_hash_fetcher=candidate_fetcher,
            )
    except Exception as exc:
        return _Outcome(
            fixture=fixture,
            source_name=source.name,
            top_score=0.0,
            top_issue_id=None,
            top_correct=None,
            n_candidates=0,
            error=f"{type(exc).__name__}: {exc}",
            hash_providers_supplied=hash_providers_supplied,
            api_call_counts=_diff_counts(counts_before, source.api_call_counts),
        )
    if not ranked:
        return _Outcome(
            fixture=fixture,
            source_name=source.name,
            top_score=0.0,
            top_issue_id=None,
            top_correct=None,
            n_candidates=0,
            hash_providers_supplied=hash_providers_supplied,
            api_call_counts=_diff_counts(counts_before, source.api_call_counts),
        )
    top = ranked[0]
    runner_up = ranked[1] if len(ranked) > 1 else None
    expected = fixture.expected.get(source.name)
    correct = (top.issue_id == expected) if expected is not None else None
    top_candidates = [
        _CandidateSummary(
            issue_id=c.issue_id,
            score=c.score,
            metadata_score=c.metadata_score,
            cover_score=c.cover_score,
            series=c.summary.series,
            summary_year=c.summary.year,
            volume_id=c.volume_id,
        )
        for c in ranked[:_TOP_K_FOR_DIAGNOSTIC]
    ]
    return _Outcome(
        fixture=fixture,
        source_name=source.name,
        top_score=top.score,
        top_issue_id=top.issue_id,
        top_correct=correct,
        n_candidates=len(ranked),
        top_metadata_score=top.metadata_score,
        top_cover_score=top.cover_score,
        runner_up_score=runner_up.score if runner_up else None,
        hash_providers_supplied=hash_providers_supplied,
        top_candidates=top_candidates,
        api_call_counts=_diff_counts(counts_before, source.api_call_counts),
    )


def _aggregate(outcomes: Iterable[_Outcome]) -> dict[str, _SourceReport]:
    reports: dict[str, _SourceReport] = defaultdict(_SourceReport)
    for o in outcomes:
        rep = reports[o.source_name]
        if o.error:
            rep.errored += 1
            continue
        if o.n_candidates == 0:
            rep.no_candidates += 1
            continue
        if o.top_correct is None:
            rep.no_expected_id += 1
            continue
        band = _band_for(o.top_score)
        bucket = rep.by_band.setdefault(band, {"correct": 0, "wrong": 0})
        if o.top_correct:
            rep.correct += 1
            bucket["correct"] += 1
        else:
            rep.wrong += 1
            bucket["wrong"] += 1
    return reports


def _format_report(reports: dict[str, _SourceReport]) -> str:
    lines: list[str] = []
    for source in sorted(reports):
        rep = reports[source]
        lines.append(f"\n=== {source} ===")
        total_with_expected = rep.correct + rep.wrong
        lines.append(f"  correct: {rep.correct}")
        lines.append(f"  wrong:   {rep.wrong}")
        if rep.no_candidates:
            lines.append(f"  no candidates returned: {rep.no_candidates}")
        if rep.no_expected_id:
            lines.append(
                f"  fixtures missing expected {source} id: {rep.no_expected_id}"
            )
        if rep.errored:
            lines.append(f"  errors: {rep.errored}")
        if total_with_expected:
            pct = 100.0 * rep.correct / total_with_expected
            lines.append(f"  accuracy on labeled fixtures: {pct:.1f}%")
        if rep.by_band:
            lines.append("  by score band:")
            for low, _high, label in _SCORE_BANDS:  # noqa: B007
                bucket = rep.by_band.get(label)
                if bucket is None:
                    continue
                total = bucket["correct"] + bucket["wrong"]
                pct = 100.0 * bucket["correct"] / total if total else 0.0
                lines.append(
                    f"    {label}: {bucket['correct']}/{total} correct ({pct:.0f}%)"
                )
    return "\n".join(lines)


def _cover_score_repr(o: _Outcome) -> str:
    """
    Render the top candidate's cover-hash status for diagnostic output.

    Distinguishes the four observable states:

    - ``"<float>"`` — hashing fired AND we got a score (the useful case).
    - ``"N/A (cover_quality != full)"`` — harness gated hashing off for
      this fixture, so the matcher only saw metadata signal.
    - ``"N/A (unambiguous metadata)"`` — providers were supplied but
      the matcher's `_should_invoke_hashing` decided ranking was already
      a clear win; hashing skipped.
    - ``"N/A (provider returned None)"`` — providers fired but produced
      no usable hash (local cover unreadable, candidate URLs all empty,
      or download/hash exceptions for every candidate).

    Inferred from `_Outcome` fields without re-querying the matcher.
    """
    if o.top_cover_score is not None:
        return f"{o.top_cover_score:.2f}"
    if not o.hash_providers_supplied:
        return "N/A (cover_quality != full)"
    # Providers were supplied; the matcher chose not to hash this
    # candidate OR hashing failed. Distinguish via the score gap: if
    # the gap is < the matcher's default disambiguation_margin (0.10),
    # we'd have expected hashing to fire — so the None means it
    # actually fired-and-failed.
    if o.runner_up_score is not None and (o.top_score - o.runner_up_score) < 0.10:
        return "N/A (provider returned None)"
    return "N/A (unambiguous metadata)"


def _format_candidate_line(rank: int, c: _CandidateSummary, expected: object) -> str:
    """One line of the top-K table — marks the expected id when present."""
    marker = " ← expected" if expected == c.issue_id else ""
    cover_repr = f"{c.cover_score:.2f}" if c.cover_score is not None else "N/A"
    # Volume/series name, cover year, and volume_id together identify
    # which reprint or variant volume a candidate came from — and let
    # us tell same-volume variants ("vol=123") apart from name
    # collisions ("vol=123" vs "vol=987"). CV issue id 476696 means
    # nothing visually, but "[Watchmen, 1987, vol=10455]" tells you
    # the volume at a glance.
    series_parts: list[str] = []
    if c.series:
        series_parts.append(c.series)
    if c.summary_year is not None:
        series_parts.append(str(c.summary_year))
    if c.volume_id is not None:
        series_parts.append(f"vol={c.volume_id}")
    series_repr = f" [{', '.join(series_parts)}]" if series_parts else ""
    return (
        f"        #{rank} id={c.issue_id} score={c.score:.2f} "
        f"(md={c.metadata_score:.2f} cover={cover_repr}){series_repr}{marker}"
    )


def _print_failed_outcomes(outcomes: list[_Outcome]) -> None:
    """Show details on wrong / errored outcomes for hand-investigation."""
    bad = [
        o
        for o in outcomes
        if (o.top_correct is False) or o.error or o.n_candidates == 0
    ]
    if not bad:
        return
    print("\n--- Outcomes worth a look ---")  # noqa: T201
    for o in bad:
        marker = "ERR" if o.error else ("MISS" if o.top_correct is False else "EMPTY")
        expected = o.fixture.expected.get(o.source_name, "?")
        lines = [
            f"  [{marker}] {o.source_name}: {o.fixture.file_path.name}",
            (
                f"      expected={expected} got={o.top_issue_id} "
                f"score={o.top_score:.2f} n={o.n_candidates}"
            ),
        ]
        if o.error:
            lines.append(f"      error: {o.error}")
        elif o.top_metadata_score is not None:
            # Diagnostic line: shows raw metadata score, cover score
            # (or why it's missing), and the gap to the runner-up.
            gap_repr = (
                f"gap={o.top_score - o.runner_up_score:.2f}"
                if o.runner_up_score is not None
                else "no runner-up"
            )
            lines.append(
                f"      metadata={o.top_metadata_score:.2f} "
                f"cover={_cover_score_repr(o)} {gap_repr}"
            )
            if o.top_candidates:
                # Show the top-K table for MISS cases. When gap is small
                # (tied or near-tied), the runner-up is usually the right
                # answer; printing its breakdown shows whether it lost on
                # cover-score, metadata, or a tiebreak.
                lines.append("      top candidates:")
                for rank, c in enumerate(o.top_candidates, start=1):
                    lines.append(_format_candidate_line(rank, c, expected))
        print("\n".join(lines))  # noqa: T201


def _print_progress(outcome: _Outcome, fixture: _Fixture) -> None:
    """Per-(fixture, source) one-line progress indicator."""
    if outcome.error:
        print(f"err ({outcome.error.split(':', 1)[0]})")  # noqa: T201
    elif outcome.top_correct:
        print(f"OK  score={outcome.top_score:.2f}")  # noqa: T201
    elif outcome.top_correct is False:
        print(f"miss expected={fixture.expected.get(outcome.source_name)} ")  # noqa: T201
    elif outcome.n_candidates == 0:
        print("no candidates returned")  # noqa: T201
    else:
        # Candidates exist but the fixture didn't ship an expected id for
        # this source, so we can't grade the result. Distinct case from
        # n=0 — used to be conflated in one message.
        print(  # noqa: T201
            f"no expected {outcome.source_name} id "
            f"(returned n={outcome.n_candidates} candidates; "
            f"top.score={outcome.top_score:.2f})"
        )


def _calibrate_loop(
    fixtures: list[_Fixture],
    sources: list[OnlineSource],
    *,
    checkpoint: Callable[[list[_Outcome]], None] | None = None,
    checkpoint_every: int = 10,
) -> list[_Outcome]:
    """
    Drive search+rank for every (fixture, source) pair, with progress + ETA.

    When `checkpoint` is supplied, the callback is invoked with the
    outcomes-so-far every `checkpoint_every` fixtures (default 10). This
    bounds work lost to a mid-run kill: at most `checkpoint_every`
    fixtures of in-memory state are lost if the process is interrupted
    between checkpoints. Combined with atomic writes in
    `_serialize_outcomes`, you can `Ctrl-C` safely and resume by
    restarting (the API cache replays already-done fixtures fast; the
    written outcomes file shows what was already saved).
    """
    outcomes: list[_Outcome] = []
    eta = _ETA(total_fixtures=len(fixtures))
    for i, fixture in enumerate(fixtures, start=1):
        if not fixture.file_path.exists():
            print(  # noqa: T201
                f"  [{i}/{len(fixtures)}] {fixture.file_path}: missing, skipping"
            )
            continue
        eta.fixture_started()
        for source in sources:
            print(  # noqa: T201
                f"  [{i}/{len(fixtures)}] {source.name}: {fixture.file_path.name}",
                end=" ... ",
                flush=True,
            )
            try:
                with _Heartbeat(f"{source.name}:{fixture.file_path.name}", eta=eta):
                    outcome = _score_one(source, fixture)
            except Exception:  # pragma: no cover — defensive
                print("ERROR")  # noqa: T201
                traceback.print_exc()
                continue
            _print_progress(outcome, fixture)
            outcomes.append(outcome)
        eta.fixture_finished()
        # After the first fixture, and at every 10th, print an overall
        # progress line so the user has a visible ETA without waiting
        # for a heartbeat tick on a slow fixture.
        if i == 1 or i % 10 == 0 or i == len(fixtures):
            print(f"  [{eta.progress_line()}]")  # noqa: T201
        # Periodic checkpoint to disk so a mid-run kill doesn't lose
        # more than `checkpoint_every` fixtures of work.
        if checkpoint is not None and i % checkpoint_every == 0 and outcomes:
            checkpoint(outcomes)
            print(  # noqa: T201
                f"  [checkpoint: {len(outcomes)} outcomes saved]"
            )
    return outcomes


def _print_cost_estimate(n_fixtures: int, sources: list[OnlineSource]) -> None:
    """
    Warn upfront about API budget and estimated wall time.

    Per fixture, each source's two-step search costs up to:

      Metron: 1 series_list + N issues_list (N ≤ _MAX_SERIES_PER_SEARCH = 20)
      CV:     1 search       + N list_issues (N ≤ _MAX_VOLUMES_PER_SEARCH = 20)

    Documented per-IP rate limits: Metron 20/min and 5,000/day, CV 1/sec
    and 200/hour. The hourly cap on CV is the binding constraint for
    multi-fixture runs; this prints the wall-time estimate so the user
    isn't surprised.
    """
    if not sources:
        return
    source_names = {s.name for s in sources}
    msgs: list[str] = []
    if "comicvine" in source_names:
        from comicbox.formats.comicvine_api.online_source import ComicVineOnlineSource

        per = 1 + ComicVineOnlineSource._MAX_VOLUMES_PER_SEARCH
        total = n_fixtures * per
        if total > 200:
            est_hours = total / 200
            msgs.append(
                f"  ComicVine: ~{total} calls worst case "
                f"(at {per}/fixture x {n_fixtures} fixtures), "
                f"vs. 200/hr cap → up to {est_hours:.1f}h wall time."
            )
        else:
            msgs.append(
                f"  ComicVine: ~{total} calls worst case "
                f"(at {per}/fixture x {n_fixtures} fixtures); 1-req/sec floor "
                f"means at least {total}s pacing."
            )
    if "metron" in source_names:
        from comicbox.formats.metron_api.online_source import MetronOnlineSource

        per = 1 + MetronOnlineSource._MAX_SERIES_PER_SEARCH
        total = n_fixtures * per
        # Metron's 20/min is the binding constraint at typical fixture counts.
        est_min = max(1.0, total / 20)
        msgs.append(
            f"  Metron: ~{total} calls worst case "
            f"(at {per}/fixture x {n_fixtures} fixtures); 20/min cap → "
            f"at least {est_min:.1f}min wall time."
        )
    if not msgs:
        return
    print("Estimated cost (worst case; cached fixtures replay free):")  # noqa: T201
    for m in msgs:
        print(m)  # noqa: T201
    print(  # noqa: T201
        "  Tip: --max-per-search N reduces per-fixture cost during smoke runs.\n"
        "       Re-running with the same fixtures replays from cache."
    )


def _resolve_retry_outcomes_path(fixtures_path: Path) -> Path:
    """
    Pick which outcomes file `--retry-misses` should read.

    Preference order:

    1. ``<stem>.outcomes.json`` (a full run's output) — the canonical
       source if it exists.
    2. ``<stem>.outcomes.partial.json`` (a filtered run's output) —
       fallback for users iterating before they've ever had budget for
       a full run (CV's 200/hr cap can make full calibration take days).

    Raises FileNotFoundError when neither exists. The error message
    names both expected paths so the user knows what to produce.
    """
    full = fixtures_path.with_suffix(".outcomes.json")
    if full.exists():
        return full
    partial = fixtures_path.with_suffix(".outcomes.partial.json")
    if partial.exists():
        return partial
    msg = (
        f"--retry-misses needs a previous run's outcomes at {full} "
        f"(or {partial.name} from a prior filtered/sampled run); "
        f"run `make calibrate` or a filtered run first."
    )
    raise FileNotFoundError(msg)


def _load_done_files(outcomes_path: Path) -> set[str]:
    """Return file paths in `outcomes_path` regardless of outcome tag."""
    if not outcomes_path.exists():
        return set()
    raw = json.loads(outcomes_path.read_text())
    return {str(entry["file"]) for entry in raw if "file" in entry}


def _filter_skip_done(fixtures: list[_Fixture], done_files: set[str]) -> list[_Fixture]:
    """Drop fixtures already present in `done_files` (resume support)."""
    return [f for f in fixtures if str(f.file_path) not in done_files]


def _resolve_resume_source_path(fixtures_path: Path, label: str | None) -> Path | None:
    """
    Pick which outcomes file `--resume` should read fixtures-done from.

    When `--label` is set, a chunked run writes to the labeled file and
    must resume from the same labeled file — even if a canonical full
    outcomes file exists, mixing the two would skip the wrong fixtures.

    When `--label` is unset, fall back to the same full-then-partial
    resolution `--retry-misses` uses. The user's first chunked run will
    accumulate into the canonical outcomes file; subsequent chunks resume
    from there.

    Returns None when nothing exists. Unlike `_resolve_retry_outcomes_path`,
    a missing source is NOT an error: a fresh `--resume` run just starts
    from the beginning.
    """
    if label:
        labeled = fixtures_path.with_suffix(f".outcomes.{label}.json")
        return labeled if labeled.exists() else None
    try:
        return _resolve_retry_outcomes_path(fixtures_path)
    except FileNotFoundError:
        return None


def _apply_filters(
    fixtures: list[_Fixture],
    *,
    fixtures_path: Path,
    retry_misses: bool,
    name_filter: str | None,
    one_per_series: bool,
    limit: int | None,
    resume: bool = False,
    label: str | None = None,
) -> list[_Fixture]:
    """
    Apply --retry-misses, --filter, --one-per-series, --resume, --limit in order.

    Raises FileNotFoundError when --retry-misses requires an outcomes
    file that doesn't exist (caller catches and reports).

    Resume semantics: when `--resume` is set, fixtures whose file path
    already appears in the resume source (labeled outcomes file when
    `--label` is set, otherwise canonical → partial fallback) are
    skipped. Lets you run the full fixture set in overnight-sized
    chunks with `--limit N` repeated: each chunk picks up where the
    previous left off, processing the next N un-done fixtures.

    Order rationale: resume runs AFTER `--one-per-series` so series
    dedup operates on the full set every chunk and picks the same
    representative each time (avoiding re-tagging the same series
    across chunks). Resume runs BEFORE `--limit` so the chunk cap
    applies to the *undone* fixtures.
    """
    if retry_misses:
        outcomes_path = _resolve_retry_outcomes_path(fixtures_path)
        miss_files = _load_miss_files(outcomes_path)
        before = len(fixtures)
        fixtures = _filter_to_misses(fixtures, miss_files)
        print(  # noqa: T201
            f"--retry-misses: filtered {before} → {len(fixtures)} fixtures "
            f"(loaded misses from {outcomes_path.name})"
        )
    if name_filter:
        pattern = re.compile(name_filter)
        before = len(fixtures)
        fixtures = [f for f in fixtures if pattern.search(f.file_path.name)]
        print(f"--filter {name_filter!r}: {before} → {len(fixtures)} fixtures")  # noqa: T201
    if one_per_series:
        before = len(fixtures)
        fixtures = _dedupe_one_per_series(fixtures)
        print(  # noqa: T201
            f"--one-per-series: {before} → {len(fixtures)} fixtures "
            f"(one representative per series prefix)"
        )
    if resume:
        resume_source = _resolve_resume_source_path(fixtures_path, label)
        if resume_source is None:
            print(  # noqa: T201
                "--resume: no existing outcomes file; starting from "
                "the beginning of the fixture set"
            )
        else:
            done_files = _load_done_files(resume_source)
            before = len(fixtures)
            fixtures = _filter_skip_done(fixtures, done_files)
            print(  # noqa: T201
                f"--resume: skipped {before - len(fixtures)} already-done "
                f"fixtures from {resume_source.name} → {len(fixtures)} remaining"
            )
    if limit:
        fixtures = fixtures[:limit]
    return fixtures


def _build_checkpoint(
    *,
    fixtures_path: Path,
    outcomes_path: Path,
    label: str | None,
    was_filtered: bool,
    resume: bool = False,
) -> Callable[[list[_Outcome]], None]:
    """
    Pick the right periodic-save callback for `_calibrate_loop`.

    Mirrors the end-of-run save logic so the checkpoint and the final
    write go to the same place. Five branches:

    - **Resume + labeled** → MERGE into `<stem>.outcomes.<label>.json`.
      Each chunk accumulates into the labeled file; the final outcomes
      file is the union of all chunks.
    - **Resume (no label)** → MERGE into the canonical
      `<stem>.outcomes.json`. Same accumulation, into the default path.
    - **Labeled run** (no resume) → OVERWRITE
      `<stem>.outcomes.<label>.json` (Phase B matrix runs).
    - **Filtered run** → MERGE into `<stem>.outcomes.partial.json` so
      iterating a subset preserves other fixtures' state.
    - **Default (full) run** → OVERWRITE the canonical
      `<stem>.outcomes.json`. Ctrl-C between checkpoints leaves the
      latest-saved version on disk.

    `--resume` always implies merge (chunks accumulate), regardless of
    `--label` or implicit filtering. Without merge, each chunk would
    overwrite the previous chunk's results — defeating the point.

    Atomicity comes from `_atomic_write_json` (used by both serializers).
    """
    if resume:
        dest = (
            fixtures_path.with_suffix(f".outcomes.{label}.json")
            if label
            else outcomes_path
        )
        return lambda outcomes: _merge_outcomes_to_partial(dest, outcomes)
    if label:
        labeled_path = fixtures_path.with_suffix(f".outcomes.{label}.json")
        return lambda outcomes: _serialize_outcomes(outcomes, labeled_path)
    if was_filtered:
        side = fixtures_path.with_suffix(".outcomes.partial.json")
        return lambda outcomes: _merge_outcomes_to_partial(side, outcomes)
    return lambda outcomes: _serialize_outcomes(outcomes, outcomes_path)


def _save_outcomes(
    outcomes: list[_Outcome],
    *,
    fixtures_path: Path,
    outcomes_path: Path,
    label: str | None,
    was_filtered: bool,
    resume: bool,
) -> None:
    """
    Save the final outcomes to whichever file the checkpointer was using.

    Mirrors `_build_checkpoint`'s branching so the final write goes to
    the same file the periodic checkpoint targeted. Prints a one-line
    confirmation describing where outcomes landed.
    """
    if resume:
        dest = (
            fixtures_path.with_suffix(f".outcomes.{label}.json")
            if label
            else outcomes_path
        )
        existed = dest.exists()
        _merge_outcomes_to_partial(dest, outcomes)
        verb = "Merged chunk into" if existed else "Saved chunk to"
        print(f"\n{verb} {dest}")  # noqa: T201
        return
    if label:
        labeled = fixtures_path.with_suffix(f".outcomes.{label}.json")
        _serialize_outcomes(outcomes, labeled)
        print(f"\nSaved labeled outcomes to {labeled}")  # noqa: T201
        return
    if not was_filtered:
        _serialize_outcomes(outcomes, outcomes_path)
        print(f"\nSaved outcomes to {outcomes_path}")  # noqa: T201
        return
    if outcomes:
        # Filtered runs MERGE into a sibling file so iterating a subset
        # (e.g. `--retry-misses --filter Watchmen`) doesn't destroy the
        # other fixtures' last-known states.
        side = fixtures_path.with_suffix(".outcomes.partial.json")
        existed = side.exists()
        _merge_outcomes_to_partial(side, outcomes)
        verb = "Merged" if existed else "Saved"
        print(f"\n{verb} partial outcomes into {side}")  # noqa: T201


def _resolve_sources(
    args_sources: str, api_budget: str | None = None
) -> list[OnlineSource]:
    """
    Build configured sources from the comicbox config.

    Skip + warn on misconfigured sources. When `api_budget` is supplied
    (typically from the `--api-budget` CLI flag), the loaded online
    settings are rebuilt with that value applied globally so every
    source's resolve_api_budget(...) reflects the experiment.
    """
    from dataclasses import replace

    from comicbox.config.settings import APIBudget

    cfg = get_config(None)
    online = cfg.online
    if api_budget is not None:
        online = replace(online, api_budget=APIBudget(api_budget))
    enabled = {n.strip() for n in args_sources.split(",") if n.strip()}
    sources: list[OnlineSource] = []
    for name in enabled:
        try:
            sources.append(_build_source(name, online))
        except RuntimeError as exc:
            sys.stderr.write(f"skipping {name}: {exc}\n")
    return sources


def _build_argparser() -> argparse.ArgumentParser:
    """All CLI flags. Extracted so `main()` stays under the C901 statement cap."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=Path(__file__).parent / "fixtures.json",
        help="Path to fixtures.json (default: tests/calibration/fixtures.json)",
    )
    parser.add_argument(
        "--sources",
        default="metron,comicvine",
        help="Comma-separated source names to calibrate against (default: both).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process at most N fixtures (useful for smoke tests).",
    )
    parser.add_argument(
        "--max-per-search",
        type=int,
        default=None,
        help=(
            "Override the per-fixture API-call cap for both sources "
            "(default 20 each; total cost per fixture is N+1). Lowering "
            "this dramatically reduces smoke-test cost — but it also "
            "narrows what's calibrated, since correct matches outside "
            "the top-N volume search will look like 'no candidates.' "
            "Use 5 for fast iteration; leave at default for production "
            "calibration."
        ),
    )
    parser.add_argument(
        "--retry-misses",
        action="store_true",
        help=(
            "Run only the fixtures that previously failed (wrong / no "
            "candidates / error) per a saved outcomes file. Prefers "
            "<fixtures-dir>/<fixtures-stem>.outcomes.json (full run); "
            "falls back to .outcomes.partial.json (filtered run) so you "
            "can iterate before a full calibration is ever finished. "
            "Useful for verifying a scoring or filter change against just "
            "the regression set rather than re-running the full fixture "
            "set (which can take days against CV's 200/hr cap)."
        ),
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Skip fixtures already present in the outcomes file (any "
            "outcome — correct, wrong, no_candidates, error). Combined "
            "with --limit N, run the full set in overnight-sized chunks: "
            "each session picks up where the previous left off. The "
            "checkpoint mechanism saves outcomes every 10 fixtures, so "
            "Ctrl-C between sessions loses at most ~10 fixtures of work. "
            "No-op when no existing outcomes file is found."
        ),
    )
    parser.add_argument(
        "--filter",
        dest="name_filter",
        default=None,
        metavar="REGEX",
        help=(
            "Run only fixtures whose file basename matches this regex. "
            "E.g. --filter 'Lois Lane|Watchmen' for a focused smoke run."
        ),
    )
    parser.add_argument(
        "--one-per-series",
        action="store_true",
        help=(
            "Dedupe fixtures by series, keeping only the first issue per "
            "series prefix (everything before the # issue marker). Six "
            "Watchmen issues, twenty Conan issues, etc. all probe the same "
            "series-discovery code path — one representative is enough for "
            "calibration. Pairs well with --retry-misses for cheap "
            "fix-verification iterations."
        ),
    )
    parser.add_argument(
        "--api-budget",
        choices=("exhaustive", "balanced", "fast"),
        default=None,
        help=(
            "Override the api_budget for ALL queried sources. Default uses "
            "whatever the config / built-in default specifies (today: "
            "'balanced'). Phase B calibration uses this to compare modes — "
            "run the matrix with --label exhaustive, then --label fast, "
            "then diff with tests/calibration/compare.py. See "
            "tasks/online-tagging/06-api-budget-spec.md."
        ),
    )
    parser.add_argument(
        "--label",
        default=None,
        metavar="NAME",
        help=(
            "Name this run for cross-run comparison. Outcomes go to "
            "<fixtures-stem>.outcomes.<label>.json instead of overwriting "
            "the canonical outcomes file. Use with --api-budget to label "
            "experiments: --api-budget fast --label fast-pf07-mv5."
        ),
    )
    return parser


def main() -> int:
    args = _build_argparser().parse_args()

    # Honor --max-per-search by patching the class-level caps. Affects all
    # sources constructed below.
    if args.max_per_search is not None:
        from comicbox.formats.comicvine_api.online_source import ComicVineOnlineSource
        from comicbox.formats.metron_api.online_source import MetronOnlineSource

        ComicVineOnlineSource._MAX_VOLUMES_PER_SEARCH = args.max_per_search
        MetronOnlineSource._MAX_SERIES_PER_SEARCH = args.max_per_search

    fixtures_path: Path = args.fixtures
    if not fixtures_path.exists():
        sys.stderr.write(
            f"fixtures file not found: {fixtures_path}\n"
            f"Copy {fixtures_path.parent}/fixtures.example.json to "
            f"{fixtures_path.name} and populate it.\n"
        )
        return 1
    fixtures = _load_fixtures(fixtures_path)
    outcomes_path = fixtures_path.with_suffix(".outcomes.json")

    try:
        fixtures = _apply_filters(
            fixtures,
            fixtures_path=fixtures_path,
            retry_misses=args.retry_misses,
            resume=args.resume,
            label=args.label,
            name_filter=args.name_filter,
            one_per_series=args.one_per_series,
            limit=args.limit,
        )
    except FileNotFoundError as exc:
        sys.stderr.write(f"{exc}\n")
        return 1

    print(f"Loaded {len(fixtures)} fixtures from {fixtures_path}")  # noqa: T201
    if not fixtures:
        sys.stderr.write("no fixtures to process after filtering; aborting\n")
        return 1

    sources = _resolve_sources(args.sources, api_budget=args.api_budget)
    if not sources:
        sys.stderr.write("no usable sources; aborting\n")
        return 1
    print(f"Calibrating against: {', '.join(s.name for s in sources)}")  # noqa: T201
    if args.api_budget is not None:
        print(f"api_budget override: {args.api_budget}")  # noqa: T201
    _print_cost_estimate(len(fixtures), sources)

    # Compute filtered status once — both the checkpoint callback and
    # the final save need it.
    was_filtered = bool(
        args.retry_misses or args.name_filter or args.limit or args.one_per_series
    )
    checkpoint = _build_checkpoint(
        fixtures_path=fixtures_path,
        outcomes_path=outcomes_path,
        label=args.label,
        was_filtered=was_filtered,
        resume=args.resume,
    )

    outcomes = _calibrate_loop(fixtures, sources, checkpoint=checkpoint)
    reports = _aggregate(outcomes)
    print(_format_report(reports))  # noqa: T201
    _print_failed_outcomes(outcomes)
    _save_outcomes(
        outcomes,
        fixtures_path=fixtures_path,
        outcomes_path=outcomes_path,
        label=args.label,
        was_filtered=was_filtered,
        resume=args.resume,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
