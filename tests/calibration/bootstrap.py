r"""
Bootstrap a fixtures.json file from comics that already carry online identifiers.

Walks one or more directories, reads each comic's existing metadata, and
emits fixture entries for any comic that has a Metron and/or ComicVine
identifier already in its tags. Saves the manual labor of typing out
hundreds of (file, expected_id) pairs by hand.

The premise: comics tagged with metron-tagger or a previous
comicbox run already know their canonical ids. We trust those ids as
ground truth for calibration. If your library is mostly hand-tagged, this
gives you a starting fixture set for free; if your library is mostly
untagged, the harness has nothing to bootstrap from and you'll need to
build fixtures.json by hand.

Usage:

    # Bootstrap from a single directory (full-cover quality):
    uv run python -m tests.calibration.bootstrap ~/Milliways/Comics/Test

    # Multiple sources, write to a specific path, mark as thumbnail-quality:
    uv run python -m tests.calibration.bootstrap \
        ~/Milliways/slimlib --cover-quality thumbnail \
        --output tests/calibration/fixtures-slim.json

    # Only emit fixtures that have BOTH metron and comicvine ids
    # (best for cross-source calibration):
    uv run python -m tests.calibration.bootstrap \
        ~/Milliways/Comics/Test --require-both

    # Smoke-test on the first 50 comics:
    uv run python -m tests.calibration.bootstrap ~/Milliways/Comics --limit 50

The output JSON is the same format `run.py` consumes; merge files by hand
(or with jq) if you want a single fixtures.json mixing cover-quality
levels.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from glom import glom
from loguru import logger

from comicbox.box import Comicbox
from comicbox.logger import init_logging

if TYPE_CHECKING:
    from collections.abc import Iterator


_COMIC_SUFFIXES = frozenset({".cbz", ".cbr", ".cbt", ".cb7", ".pdf"})
_DEFAULT_OUTPUT = Path("tests/calibration/fixtures.json")


def _coerce_int(value: Any) -> int | None:
    """Defensive int coercion — identifier keys are sometimes str."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def extract_identifiers(comic_path: Path) -> tuple[int | None, int | None]:
    """
    Return (metron_id, comicvine_id) from a comic's existing tags.

    Reads the comic via comicbox's normal merge pipeline. Online lookup
    is off by default, so this never hits the network — purely a tag
    read. Returns (None, None) for comics with neither identifier.
    """
    try:
        with Comicbox(comic_path) as cb:
            merged: Any = cb.get_merged_metadata()
            md = dict(merged) if merged else {}
    except Exception as exc:
        logger.warning(f"{comic_path}: read failed: {exc}")
        return (None, None)
    metron = _coerce_int(glom(md, "comicbox.identifiers.metron.key", default=None))
    cv = _coerce_int(glom(md, "comicbox.identifiers.comicvine.key", default=None))
    return (metron, cv)


def iter_comics(paths: list[Path]) -> Iterator[Path]:
    """Yield comic paths under each input (file or directory), sorted, deduped."""
    seen: set[Path] = set()
    for raw in paths:
        path = raw.expanduser()
        if path.is_file():
            if path.suffix.lower() in _COMIC_SUFFIXES and path not in seen:
                seen.add(path)
                yield path
        elif path.is_dir():
            for f in sorted(path.rglob("*")):
                if (
                    f.is_file()
                    and f.suffix.lower() in _COMIC_SUFFIXES
                    and f not in seen
                ):
                    seen.add(f)
                    yield f
        else:
            logger.warning(f"{path}: not a file or directory, skipping")


def _build_fixture(
    comic_path: Path,
    metron_id: int | None,
    cv_id: int | None,
    cover_quality: str,
) -> dict[str, Any]:
    """Format one fixture entry. None ids are emitted as JSON null."""
    return {
        "file": str(comic_path),
        "metron": metron_id,
        "comicvine": cv_id,
        "cover_quality": cover_quality,
    }


def _should_keep(
    metron_id: int | None,
    cv_id: int | None,
    *,
    require_both: bool,
) -> bool:
    """Bootstrap policy: at least one id required; both required if --require-both."""
    if metron_id is None and cv_id is None:
        return False
    return not (require_both and (metron_id is None or cv_id is None))


def bootstrap(
    paths: list[Path],
    *,
    cover_quality: str = "full",
    limit: int | None = None,
    require_both: bool = False,
) -> list[dict[str, Any]]:
    """
    Walk paths, extract ids, return a list of fixture entries.

    Reports progress to stdout. Errors during read are logged at WARNING
    and the comic is skipped — one bad CBR shouldn't tank the whole run.
    """
    fixtures: list[dict[str, Any]] = []
    n_seen = 0
    n_no_ids = 0
    for comic_path in iter_comics(paths):
        if limit is not None and len(fixtures) >= limit:
            break
        n_seen += 1
        if n_seen % 50 == 0:
            print(  # noqa: T201
                f"  scanned {n_seen}, kept {len(fixtures)}, skipped {n_no_ids} (no ids)"
            )
        metron_id, cv_id = extract_identifiers(comic_path)
        if not _should_keep(metron_id, cv_id, require_both=require_both):
            n_no_ids += 1
            continue
        fixtures.append(_build_fixture(comic_path, metron_id, cv_id, cover_quality))
    print(  # noqa: T201
        f"\nFinal: scanned {n_seen}, kept {len(fixtures)}, skipped {n_no_ids} (no ids)"
    )
    return fixtures


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
        "--cover-quality",
        choices=("full", "thumbnail", "missing"),
        default="full",
        help=(
            "Cover-quality tag applied to all generated entries. Use "
            "'thumbnail' for shrunk-cover libraries (e.g. slimlib). The "
            "calibration harness uses this to skip cover-hash testing on "
            "degraded covers."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Stop after generating N fixtures (useful for sampling a large library).",
    )
    parser.add_argument(
        "--require-both",
        action="store_true",
        help=(
            "Only emit fixtures that have BOTH metron and comicvine ids. "
            "Best for cross-source calibration."
        ),
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress comicbox INFO log output during the scan.",
    )
    args = parser.parse_args()

    if args.quiet:
        init_logging("WARNING")
    else:
        init_logging("INFO")

    fixtures = bootstrap(
        args.paths,
        cover_quality=args.cover_quality,
        limit=args.limit,
        require_both=args.require_both,
    )
    if not fixtures:
        sys.stderr.write(
            "No comics with metron or comicvine identifiers found. "
            "Either your library is mostly untagged or the comics aren't "
            "tagged with these specific online sources.\n"
        )
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(fixtures, indent=2) + "\n")
    print(f"\nWrote {len(fixtures)} fixtures to {args.output}")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
