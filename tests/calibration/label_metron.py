r"""
Augment a fixtures.json with Metron ids via Metron's `cv_id` filter.

CV-tagged libraries (slimlib being the motivating example) carry only
ComicVine ids in their tags. Metron's API supports filtering issues by
``cv_id`` — i.e. "give me the Metron issue that cross-references this CV
issue id." For comics that exist on both services this lets us recover
Metron ground-truth ids cheaply without manual lookup.

Without this pass, calibrating Metron against a CV-tagged library
produces ~0 gradeable outcomes — every fixture is recorded as
"no_expected_id" because the fixture didn't list a Metron id even
though the comic might be in Metron's database. After this pass:

- Fixtures with a CV id that Metron cross-references get the Metron id
  added (gradeable on the next calibration run).
- Fixtures with no Metron coverage stay metron-null (correctly excluded
  from Metron's accuracy metric instead of polluting it as "no
  candidates").

This is a one-time labeling pass — run after sample/bootstrap, then
re-run calibration. It's safe to re-run later: Metron-cached calls are
free and existing Metron ids in the fixture file are preserved.

Cost: one Metron API call per CV-only fixture. Metron's documented
limits (20/min and 5,000/day) cap throughput at ~1,200/hour, so a
500-fixture run takes ~25 minutes worst case; smaller in practice
because mokkari's cache replays repeated lookups for free.

Usage:

    uv run python -m tests.calibration.label_metron \\
        --fixtures tests/calibration/fixtures-slimlib.json

    # Preview what would change without writing:
    uv run python -m tests.calibration.label_metron \\
        --fixtures tests/calibration/fixtures-slimlib.json --dry-run

After labeling, you'll typically want to clear the existing Metron
outcomes (or run with `--label fresh` on the next chunk) so the
already-graded fixtures get re-graded with their new Metron ids.
``--retry-misses`` won't pick them up — the prior outcome was
``no_expected_id``, which isn't a miss tag.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from comicbox.config import get_config
from comicbox.formats.base.online.retry import with_retry
from comicbox.formats.metron_api.online_source import MetronOnlineSource

if TYPE_CHECKING:
    from collections.abc import Iterable

    from mokkari.session import Session


# Mokkari pages issues_list in 28-record pages by default. A cv_id
# query should return ≤1 issue in practice (CV ids are issue-scoped),
# but Metron's catalog can have duplicates from data-import quirks;
# we ask for the first page and log a warning if more than one came
# back.
_EXPECTED_HITS_MAX: int = 1


@dataclass(slots=True)
class _LabelStats:
    """Per-run counters for the end-of-run summary."""

    total: int = 0
    already_labeled: int = 0
    skipped_no_cv: int = 0
    labeled: int = 0
    not_found: int = 0
    errored: int = 0


def _build_metron_session() -> Session:
    """
    Return a configured mokkari Session.

    Reuses `MetronOnlineSource`'s session-construction logic so credentials,
    cache directory, and rate-limit bucket all match the production
    online-lookup path. The matcher's per-fixture cache will hit on
    repeated lookups within the same session.
    """
    online = get_config(None).online
    creds = online.auth.sources.get("metron")
    if creds is None:
        msg = "no Metron credentials configured (env or ~/.config/comicbox/config.yaml)"
        raise RuntimeError(msg)
    source = MetronOnlineSource(creds, online)
    if not source.is_configured():
        msg = "Metron credentials incomplete (need both username and password)"
        raise RuntimeError(msg)
    return source._get_session()


@with_retry()
def _issues_list_by_cv_id(session: Session, cv_id: int) -> list:
    """
    Run the Metron `issues_list(cv_id=...)` call with auto-retry.

    `@with_retry()` catches RateLimitError, honors the server's
    `retry_after` hint, and replays the call — same pattern the
    matcher uses in production. Without this wrapper, Metron's 20/min
    cap would cause the labeler to silently mark cv_ids as "no
    metron coverage" whenever rate-limiting kicked in (false negative
    on the calibration ground truth).
    """
    return list(session.issues_list({"cv_id": cv_id}))


def lookup_metron_by_cv_id(session: Session, cv_id: int) -> int | None:
    """
    Return the Metron issue id cross-referencing `cv_id`, or None.

    Metron's API supports filtering `/api/issue/` by `cv_id`. A clean
    cross-reference returns exactly one issue; ambiguous responses (>1
    hit) log a warning and fall back to the first result — better than
    skipping the comic entirely.

    Rate-limit errors auto-retry via `_issues_list_by_cv_id`'s
    `@with_retry()` wrapper. Only non-retriable failures (auth errors,
    bad params) or exhausted retry budgets reach this function's
    `except Exception` branch.
    """
    try:
        results = _issues_list_by_cv_id(session, cv_id)
    except Exception as exc:
        print(  # noqa: T201
            f"  ! Metron lookup failed for cv_id={cv_id}: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return None
    if not results:
        return None
    if len(results) > _EXPECTED_HITS_MAX:
        print(  # noqa: T201
            f"  ! cv_id={cv_id} matched {len(results)} Metron issues; "
            f"using first ({results[0].id})",
            file=sys.stderr,
        )
    return int(results[0].id)


def _iter_labelable(
    fixtures: list[dict[str, Any]],
) -> Iterable[tuple[int, dict[str, Any]]]:
    """
    Yield (index, fixture) pairs for fixtures that need a Metron lookup.

    Skips fixtures that already have a Metron id (idempotent re-runs)
    or that lack a CV id to cross-reference from.
    """
    for i, fixture in enumerate(fixtures):
        cv_id = fixture.get("comicvine")
        metron_id = fixture.get("metron")
        if metron_id is not None:
            continue
        if not cv_id:
            continue
        yield i, fixture


def _atomic_write_fixtures(path: Path, fixtures: list[dict[str, Any]]) -> None:
    """Write JSON to `path` atomically (temp file + rename)."""
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_text(json.dumps(fixtures, indent=2) + "\n")
    tmp.replace(path)


def label_fixtures(
    fixtures_path: Path,
    *,
    dry_run: bool = False,
    limit: int | None = None,
) -> _LabelStats:
    """
    Read fixtures.json, cross-reference CV-only entries against Metron, write back.

    Prints one progress line per lookup. With `limit`, processes at
    most N lookups (useful for smoke-testing the script itself). With
    `dry_run`, prints what would change but doesn't touch the file.
    """
    raw = json.loads(fixtures_path.read_text())
    if not isinstance(raw, list):
        msg = f"{fixtures_path}: expected a JSON list of fixtures"
        raise TypeError(msg)

    session = _build_metron_session()
    stats = _LabelStats(total=len(raw))
    pending = list(_iter_labelable(raw))
    stats.already_labeled = sum(1 for f in raw if f.get("metron") is not None)
    stats.skipped_no_cv = sum(
        1 for f in raw if f.get("metron") is None and not f.get("comicvine")
    )

    if not pending:
        print("No fixtures to label (all have Metron ids or no CV id).")  # noqa: T201
        return stats

    print(  # noqa: T201
        f"Labeling {len(pending)} fixtures against Metron's cv_id index "
        f"({stats.already_labeled} already labeled, "
        f"{stats.skipped_no_cv} skipped — no CV id)..."
    )

    for n, (i, fixture) in enumerate(pending, start=1):
        if limit is not None and n > limit:
            print(f"  reached --limit {limit}, stopping early")  # noqa: T201
            break
        cv_id = int(fixture["comicvine"])
        file_name = Path(str(fixture.get("file", ""))).name or f"#{i}"
        print(  # noqa: T201
            f"  [{n}/{len(pending)}] cv_id={cv_id} ({file_name}) ... ",
            end="",
            flush=True,
        )
        metron_id = lookup_metron_by_cv_id(session, cv_id)
        if metron_id is None:
            stats.not_found += 1
            print("no metron coverage")  # noqa: T201
            continue
        fixture["metron"] = metron_id
        stats.labeled += 1
        print(f"→ metron={metron_id}")  # noqa: T201
        # Persist incrementally so a Ctrl-C mid-run preserves what's
        # been learned so far. Atomic write means the file is never
        # left half-updated. Cost is small (a few KB rewritten per
        # lookup); benefit is huge (~25-minute runs stay safe).
        if not dry_run:
            _atomic_write_fixtures(fixtures_path, raw)

    if dry_run:
        print("\n[dry-run] no file changes written.")  # noqa: T201
    return stats


def _print_summary(stats: _LabelStats, fixtures_path: Path) -> None:
    """Render an end-of-run report; mirrors the harness's reporting style."""
    print("\n=== Metron labeling summary ===")  # noqa: T201
    print(f"  total fixtures:           {stats.total}")  # noqa: T201
    print(  # noqa: T201
        f"  already had metron id:    {stats.already_labeled}"
    )
    print(f"  no cv id (skipped):       {stats.skipped_no_cv}")  # noqa: T201
    print(f"  newly labeled:            {stats.labeled}")  # noqa: T201
    print(f"  metron has no coverage:   {stats.not_found}")  # noqa: T201
    if stats.errored:
        print(f"  errored:                  {stats.errored}")  # noqa: T201
    if stats.labeled:
        print(f"\nUpdated {fixtures_path} with {stats.labeled} new Metron ids.")  # noqa: T201


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixtures",
        type=Path,
        required=True,
        help="Path to the fixtures.json to augment in place.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Show what would be labeled without writing anything. "
            "Useful for previewing the cost of a full run."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Stop after N lookups (useful for testing the script "
            "against a few fixtures before committing to a full run)."
        ),
    )
    args = parser.parse_args()

    if not args.fixtures.exists():
        sys.stderr.write(f"fixtures file not found: {args.fixtures}\n")
        return 1

    try:
        stats = label_fixtures(args.fixtures, dry_run=args.dry_run, limit=args.limit)
    except RuntimeError as exc:
        sys.stderr.write(f"{exc}\n")
        return 1
    _print_summary(stats, args.fixtures)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
