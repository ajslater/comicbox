r"""
Stratified one-per-series fixture sampler for very large comic libraries.

The `bootstrap.py` module bulk-extracts every tagged comic into a
fixtures.json — fine for a few hundred comics, but a ~17,500-comic
library would take 38+ days to calibrate even under `fast` budget (CV's
200/hr cap is the binding constraint). At that scale we need a
*sampled* fixture set: one representative per series, balanced across
publishers and decades so the calibration covers the long tail rather
than overweighting the modern-Marvel bulge.

This sampler:

1. **Walks** the library and reads each comic's existing tags (series,
   publisher, year, metron_id, cv_id). Reuses `bootstrap.extract_identifiers`.
2. **Filters** to comics with a series name AND at least one online id
   (calibration needs ground truth — comics without an expected id
   can't be graded).
3. **Dedupes by series**: keeps the alphabetically-first comic per
   series name. Multiple issues of the same series all probe the same
   discovery code path; one representative is enough.
4. **Buckets by (decade, publisher)**: each series falls into one
   bucket based on its representative comic's cover year and publisher.
5. **Round-robins** across buckets: each round picks one (random
   within bucket) from each bucket, until the target count is reached
   or all buckets exhaust. Gives ~equal weight per bucket regardless
   of bucket size — critical when 60% of the library is Marvel-2010s
   and 1% is pre-1980 indie.

Usage:

    # Sample 500 fixtures from slimlib, write to the default location:
    uv run python -m tests.calibration.sample \\
        ~/Milliways/Comics/slimlib \\
        --count 500 \\
        --cover-quality thumbnail \\
        --output tests/calibration/fixtures-slimlib.json

    # Reproducible sample for cross-run comparison:
    uv run python -m tests.calibration.sample ~/Milliways/Comics/slimlib \\
        --count 1000 --seed 42

The output fixtures.json plugs straight into `run.py`. Combine with
`run.py --resume --limit 250` to chunk through the sample in
overnight-sized pieces.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from glom import glom
from loguru import logger

from comicbox.box import Comicbox
from comicbox.logger import init_logging
from tests.calibration.bootstrap import iter_comics

if TYPE_CHECKING:
    from collections.abc import Iterable


def _coerce_int(value: Any) -> int | None:
    """Defensive int coercion — identifier/year keys are sometimes str."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


_DEFAULT_OUTPUT = Path("tests/calibration/fixtures-slimlib.json")
_UNKNOWN_PUBLISHER = "unknown"
_UNKNOWN_DECADE = "unknown"

# Decade buckets. Tail years collapse into a single "pre-1980" bucket
# because the long pre-WWII / Golden Age / Silver Age slice is sparse in
# typical libraries — finer-grained buckets there would just produce
# empty cells that drop out of round-robin sampling. Modern decades get
# their own bucket each because that's where the library bulge lives,
# and we want stratification to *fight* the bulge.
_DECADE_BUCKETS: tuple[tuple[int, int, str], ...] = (
    (0, 1980, "pre-1980"),
    (1980, 1990, "1980s"),
    (1990, 2000, "1990s"),
    (2000, 2010, "2000s"),
    (2010, 2020, "2010s"),
    (2020, 2100, "2020s+"),
)


@dataclass(frozen=True, slots=True)
class _Comic:
    """Metadata slice extracted per comic; one per file."""

    file_path: Path
    series: str
    publisher: str
    year: int | None
    metron_id: int | None
    cv_id: int | None


def _decade_bucket(year: int | None) -> str:
    """Map a year to its decade bucket; 'unknown' for missing years."""
    if year is None:
        return _UNKNOWN_DECADE
    for low, high, label in _DECADE_BUCKETS:
        if low <= year < high:
            return label
    return _UNKNOWN_DECADE


def _extract_metadata(comic_path: Path) -> _Comic | None:
    """
    Read series, publisher, year, and online ids from a comic.

    Returns None when the comic has no series name OR no online ids
    (calibration can't grade an unidentified comic). Errors during
    read log a warning and skip the comic.
    """
    try:
        with Comicbox(comic_path) as cb:
            merged: Any = cb.get_merged_metadata()
            md = dict(merged) if merged else {}
    except Exception as exc:
        logger.warning(f"{comic_path}: read failed: {exc}")
        return None
    series = glom(md, "comicbox.series.name", default=None)
    if not series:
        return None
    metron_id = _coerce_int(glom(md, "comicbox.identifiers.metron.key", default=None))
    cv_id = _coerce_int(glom(md, "comicbox.identifiers.comicvine.key", default=None))
    if metron_id is None and cv_id is None:
        return None
    publisher = glom(md, "comicbox.publisher.name", default=None) or _UNKNOWN_PUBLISHER
    year_raw = glom(md, "comicbox.date.year", default=None)
    year = _coerce_int(year_raw)
    return _Comic(
        file_path=comic_path,
        series=str(series),
        publisher=str(publisher),
        year=year,
        metron_id=metron_id,
        cv_id=cv_id,
    )


def _dedupe_by_series(comics: Iterable[_Comic]) -> list[_Comic]:
    """
    Keep the alphabetically-first comic per series name.

    Multiple issues of the same series probe the same series-discovery
    code path in the matcher — one representative is enough for
    calibration. Alphabetical-first is deterministic; combined with a
    fixed seed in `_stratified_sample`, the whole pipeline is
    reproducible.
    """
    by_series: dict[str, _Comic] = {}
    for comic in comics:
        existing = by_series.get(comic.series)
        if existing is None or str(comic.file_path) < str(existing.file_path):
            by_series[comic.series] = comic
    return list(by_series.values())


def _bucket_key(comic: _Comic) -> tuple[str, str]:
    """(decade, publisher) bucket label."""
    return (_decade_bucket(comic.year), comic.publisher)


def _stratified_sample(
    comics: list[_Comic], target: int, *, seed: int = 0
) -> list[_Comic]:
    """
    Round-robin across (decade, publisher) buckets up to `target` total.

    Each round pulls one comic from each non-empty bucket (shuffled
    within bucket using `seed`). Buckets exhaust at different rates —
    sparse pre-1980-indie burns out fast, modern-Marvel keeps producing.
    The round-robin gives buckets equal *opportunity*: the resulting
    sample's bucket distribution is ~uniform up to bucket size.

    Returns at most `target` comics; fewer when the union of buckets
    is smaller than `target`.
    """
    buckets: dict[tuple[str, str], list[_Comic]] = defaultdict(list)
    for comic in comics:
        buckets[_bucket_key(comic)].append(comic)
    # Deterministic shuffling for in-bucket order. The sampling is for
    # diversity, not security — S311's warning about crypto-unsafe RNG
    # doesn't apply.
    rng = random.Random(seed)  # noqa: S311
    for bucket in buckets.values():
        rng.shuffle(bucket)
    out: list[_Comic] = []
    indices = dict.fromkeys(buckets, 0)
    while len(out) < target:
        progress = False
        for key, bucket in buckets.items():
            if len(out) >= target:
                break
            i = indices[key]
            if i < len(bucket):
                out.append(bucket[i])
                indices[key] = i + 1
                progress = True
        if not progress:
            break
    return out


def _summarize_buckets(comics: Iterable[_Comic]) -> dict[tuple[str, str], int]:
    """Bucket label → count of comics in that bucket. For pre/post reporting."""
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for comic in comics:
        counts[_bucket_key(comic)] += 1
    return dict(counts)


def _format_bucket_report(title: str, counts: dict[tuple[str, str], int]) -> str:
    """Tabulate bucket counts for stdout diagnostic."""
    if not counts:
        return f"{title}: (empty)"
    lines = [f"{title}:"]
    # Sort by decade then publisher for stable, readable output.
    # Decades come out as strings, so use the bucket-table order as
    # the sort key (with "unknown" pushed to the end).
    decade_order = {label: i for i, (_, _, label) in enumerate(_DECADE_BUCKETS)}
    decade_order[_UNKNOWN_DECADE] = len(_DECADE_BUCKETS)

    def sort_key(item: tuple[tuple[str, str], int]) -> tuple[int, str]:
        decade, publisher = item[0]
        return (decade_order.get(decade, 99), publisher)

    for (decade, publisher), n in sorted(counts.items(), key=sort_key):
        lines.append(f"    {decade:<10} {publisher:<30} {n:>4}")
    lines.append(f"  total buckets: {len(counts)}")
    lines.append(f"  total comics:  {sum(counts.values())}")
    return "\n".join(lines)


def _build_fixture(comic: _Comic, cover_quality: str) -> dict[str, Any]:
    """Format one fixture entry from a sampled comic."""
    return {
        "file": str(comic.file_path),
        "metron": comic.metron_id,
        "comicvine": comic.cv_id,
        "cover_quality": cover_quality,
    }


def _scan_comics(paths: list[Path], *, scan_limit: int | None) -> list[_Comic]:
    """Walk paths, extract metadata, return the usable comics with periodic logging."""
    comics: list[_Comic] = []
    scanned = 0
    for comic_path in iter_comics(paths):
        if scan_limit is not None and scanned >= scan_limit:
            break
        scanned += 1
        if scanned % 200 == 0:
            print(f"  scanned {scanned}, kept {len(comics)} usable")  # noqa: T201
        meta = _extract_metadata(comic_path)
        if meta is not None:
            comics.append(meta)
    print(  # noqa: T201
        f"Scanned {scanned} comics; {len(comics)} have series + at least one id."
    )
    return comics


def sample(
    paths: list[Path],
    *,
    count: int,
    cover_quality: str,
    seed: int,
    scan_limit: int | None,
    verbose: bool,
) -> list[dict[str, Any]]:
    """
    Walk paths, extract metadata, dedupe by series, stratify-sample to `count`.

    `scan_limit` caps how many comics the walker reads (None = full
    scan); useful for smoke runs that want a representative output
    without waiting on a 17k-comic walk.
    """
    print(f"Walking comics under: {', '.join(str(p) for p in paths)}")  # noqa: T201
    comics = _scan_comics(paths, scan_limit=scan_limit)
    if not comics:
        return []

    deduped = _dedupe_by_series(comics)
    print(f"Deduped to {len(deduped)} unique series.")  # noqa: T201
    if verbose:
        print(_format_bucket_report("Pre-sample buckets", _summarize_buckets(deduped)))  # noqa: T201

    sampled = _stratified_sample(deduped, count, seed=seed)
    print(f"Sampled {len(sampled)} comics (target {count}, seed {seed}).")  # noqa: T201
    if verbose:
        print(_format_bucket_report("Sampled buckets", _summarize_buckets(sampled)))  # noqa: T201

    return [_build_fixture(c, cover_quality) for c in sampled]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="Files or directories to scan. Directories are walked recursively.",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=_DEFAULT_OUTPUT,
        help=f"Where to write the fixtures.json (default: {_DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=500,
        help=(
            "Target sample size (default: 500). Caps the output; sampling "
            "may produce fewer when the union of (decade, publisher) "
            "buckets is smaller."
        ),
    )
    parser.add_argument(
        "--cover-quality",
        choices=("full", "thumbnail", "missing"),
        default="thumbnail",
        help=(
            "Cover-quality tag for emitted fixtures (default: thumbnail, "
            "matching slimlib-style libraries with shrunken covers). "
            "The harness uses this to skip cover-hash testing on degraded "
            "covers — calibration stays metadata-only."
        ),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help=(
            "RNG seed for in-bucket shuffling (default: 0). Pin to make "
            "the sample reproducible across runs of this script."
        ),
    )
    parser.add_argument(
        "--scan-limit",
        type=int,
        default=None,
        help=(
            "Stop the directory walk after scanning N comics. Useful for "
            "smoke-testing the sampler itself without a full library walk; "
            "the sampled output is degraded since later comics never get a "
            "chance."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print pre-sample and post-sample bucket distributions.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress comicbox INFO log output during the scan.",
    )
    args = parser.parse_args()

    init_logging("WARNING" if args.quiet else "INFO")

    fixtures = sample(
        args.paths,
        count=args.count,
        cover_quality=args.cover_quality,
        seed=args.seed,
        scan_limit=args.scan_limit,
        verbose=args.verbose,
    )
    if not fixtures:
        sys.stderr.write(
            "No usable comics found (need series name + at least one online "
            "id). Either your library is mostly untagged or the comics aren't "
            "tagged with metron / comicvine identifiers.\n"
        )
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(fixtures, indent=2) + "\n")
    print(f"\nWrote {len(fixtures)} fixtures to {args.output}")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
