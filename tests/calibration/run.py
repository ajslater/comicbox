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
import sys
import threading
import time
import traceback
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Self

from comicbox.box import Comicbox
from comicbox.config import get_config
from comicbox.online.matcher import OnlineMatcher
from comicbox.online.sources.comicvine import ComicVineOnlineSource
from comicbox.online.sources.metron import MetronOnlineSource

if TYPE_CHECKING:
    from collections.abc import Iterable

    from comicbox.config.settings import OnlineSettings
    from comicbox.online.profile import Candidate, ComicProfile
    from comicbox.online.sources.base import OnlineSource


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


@dataclass(slots=True)
class _SourceReport:
    correct: int = 0
    wrong: int = 0
    no_candidates: int = 0
    errored: int = 0
    no_expected_id: int = 0  # fixture didn't list this source
    by_band: dict[str, dict[str, int]] = field(default_factory=dict)


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


def _build_profile(comic_path: Path) -> ComicProfile:
    """
    Build a ComicProfile by letting comicbox merge the comic's tags + filename.

    `get_merged_metadata()` runs the read/normalize pipeline. Online
    lookup itself stays disabled (it's off by default), so this is purely
    a "what would comicbox extract from this file's existing tags + name"
    operation. Then we read the per-source normalized state via the
    mixin's private `_build_profile`.
    """
    with Comicbox(comic_path) as cb:
        cb.get_merged_metadata()
        return cb._build_profile()


class _Heartbeat:
    """
    Background thread that prints a "still working" hint at intervals.

    The pyrate_limiter buckets in mokkari/simyan can park a single API
    call for up to an hour when an hourly cap is hit. Without this hint,
    the user sees a stalled-looking line and has no idea whether the
    process is wedged or just being polite.
    """

    def __init__(self, label: str, *, interval: float = 15.0) -> None:
        self._label = label
        self._interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._start = time.monotonic()

    def __enter__(self) -> Self:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._thread.join(timeout=self._interval + 1.0)

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            elapsed = time.monotonic() - self._start
            print(  # noqa: T201
                f"\n      [..still working on {self._label}, {elapsed:.0f}s elapsed]",
                flush=True,
            )


def _score_one(
    source: OnlineSource,
    fixture: _Fixture,
) -> _Outcome:
    """Run search + rank on a fixture; produce an outcome."""
    try:
        profile = _build_profile(fixture.file_path)
        candidates: list[Candidate] = source.search(profile)
        # Rank using the same parameters comicbox would use in production.
        # No cover hashing here — calibration covers may be degraded
        # (slimlib) and we want a stable metadata-first signal anyway.
        ranked = OnlineMatcher().rank(profile, candidates)
    except Exception as exc:
        return _Outcome(
            fixture=fixture,
            source_name=source.name,
            top_score=0.0,
            top_issue_id=None,
            top_correct=None,
            n_candidates=0,
            error=f"{type(exc).__name__}: {exc}",
        )
    if not ranked:
        return _Outcome(
            fixture=fixture,
            source_name=source.name,
            top_score=0.0,
            top_issue_id=None,
            top_correct=None,
            n_candidates=0,
        )
    top = ranked[0]
    expected = fixture.expected.get(source.name)
    correct = (top.issue_id == expected) if expected is not None else None
    return _Outcome(
        fixture=fixture,
        source_name=source.name,
        top_score=top.score,
        top_issue_id=top.issue_id,
        top_correct=correct,
        n_candidates=len(ranked),
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
        print(  # noqa: T201
            f"  [{marker}] {o.source_name}: {o.fixture.file_path.name}\n"
            f"      expected={expected} got={o.top_issue_id} "
            f"score={o.top_score:.2f} n={o.n_candidates}"
            + (f"\n      error: {o.error}" if o.error else "")
        )


def _print_progress(outcome: _Outcome, fixture: _Fixture) -> None:
    """Per-(fixture, source) one-line progress indicator."""
    if outcome.error:
        print(f"err ({outcome.error.split(':', 1)[0]})")  # noqa: T201
    elif outcome.top_correct:
        print(f"OK  score={outcome.top_score:.2f}")  # noqa: T201
    elif outcome.top_correct is False:
        print(f"miss expected={fixture.expected.get(outcome.source_name)} ")  # noqa: T201
    else:
        print(f"no candidates / no labeled id (n={outcome.n_candidates})")  # noqa: T201


def _calibrate_loop(
    fixtures: list[_Fixture], sources: list[OnlineSource]
) -> list[_Outcome]:
    """Drive search+rank for every (fixture, source) pair, with progress."""
    outcomes: list[_Outcome] = []
    for i, fixture in enumerate(fixtures, start=1):
        if not fixture.file_path.exists():
            print(  # noqa: T201
                f"  [{i}/{len(fixtures)}] {fixture.file_path}: missing, skipping"
            )
            continue
        for source in sources:
            print(  # noqa: T201
                f"  [{i}/{len(fixtures)}] {source.name}: {fixture.file_path.name}",
                end=" ... ",
                flush=True,
            )
            try:
                with _Heartbeat(f"{source.name}:{fixture.file_path.name}"):
                    outcome = _score_one(source, fixture)
            except Exception:  # pragma: no cover — defensive
                print("ERROR")  # noqa: T201
                traceback.print_exc()
                continue
            _print_progress(outcome, fixture)
            outcomes.append(outcome)
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
        from comicbox.online.sources.comicvine import ComicVineOnlineSource

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
        from comicbox.online.sources.metron import MetronOnlineSource

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


def _resolve_sources(args_sources: str) -> list[OnlineSource]:
    """Build configured sources from the comicbox config; skip + warn on misconfigured."""
    cfg = get_config(None)
    enabled = {n.strip() for n in args_sources.split(",") if n.strip()}
    sources: list[OnlineSource] = []
    for name in enabled:
        try:
            sources.append(_build_source(name, cfg.online))
        except RuntimeError as exc:
            sys.stderr.write(f"skipping {name}: {exc}\n")
    return sources


def main() -> int:
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
    args = parser.parse_args()

    # Honor --max-per-search by patching the class-level caps. Affects all
    # sources constructed below.
    if args.max_per_search is not None:
        from comicbox.online.sources.comicvine import ComicVineOnlineSource
        from comicbox.online.sources.metron import MetronOnlineSource

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
    if args.limit:
        fixtures = fixtures[: args.limit]
    print(f"Loaded {len(fixtures)} fixtures from {fixtures_path}")  # noqa: T201

    sources = _resolve_sources(args.sources)
    if not sources:
        sys.stderr.write("no usable sources; aborting\n")
        return 1
    print(f"Calibrating against: {', '.join(s.name for s in sources)}")  # noqa: T201
    _print_cost_estimate(len(fixtures), sources)

    outcomes = _calibrate_loop(fixtures, sources)
    reports = _aggregate(outcomes)
    print(_format_report(reports))  # noqa: T201
    _print_failed_outcomes(outcomes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
