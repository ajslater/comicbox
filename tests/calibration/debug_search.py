r"""
Debug a single fixture's search path against one source.

Usage:

    uv run python -m tests.calibration.debug_search \\
        ~/Milliways/.../Lois\\ Lane\\ \\(2019\\)\\ \\#001.cbz \\
        --source metron

Prints:

  1. The ComicProfile comicbox builds from the comic's tags + filename.
  2. The exact search call we're issuing (what Metron / CV sees).
  3. The raw response — count and the first few results.
  4. A series of diagnostic variants ("just Lois Lane", "Lois Lane 2019",
     etc.) so we can see what filter shape actually works.

Useful when calibration shows 0-candidate results that "should" hit the
DB. Hit-list of suspicions this script will distinguish:

  - profile.series has parens / year suffix that breaks the API filter
  - the API is being called with the wrong param name
  - the cache is serving a stale empty response
  - the API genuinely doesn't have it (no candidates at any variant)
"""

# pyright: reportAttributeAccessIssue=false, reportArgumentType=false

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from comicbox.box import Comicbox
from comicbox.config import get_config
from comicbox.formats.comicvine_api.online_source import ComicVineOnlineSource
from comicbox.formats.metron_api.online_source import MetronOnlineSource


def _print_profile(comic_path: Path) -> object:
    print(f"=== Profile from comicbox merge ({comic_path.name}) ===")  # noqa: T201
    with Comicbox(comic_path) as cb:
        cb.get_merged_metadata()
        profile = cb._build_profile()
    for field in (
        "series",
        "issue",
        "issue_int",
        "year",
        "publisher",
        "page_count",
        "volume",
    ):
        print(f"  {field:>12}: {getattr(profile, field)!r}")  # noqa: T201
    return profile


def _build_issues_list_params(profile: object, series_id: int) -> dict[str, object]:
    """Mirror production's `_build_issue_params` for a single series."""
    from comicbox.formats.base.online.profile import strip_issue_leading_zeros

    # `series_id` is the correct Metron API filter for the FK to series.
    # `series` (mokkari's docstring example) is silently ignored — see
    # metron.py's `_build_issue_params` for the bug history.
    params: dict[str, object] = {"series_id": series_id}
    issue_number = getattr(profile, "issue", None)
    if issue_number:
        stripped = strip_issue_leading_zeros(issue_number)
        if stripped:
            params["number"] = stripped
    profile_year = getattr(profile, "year", None)
    if profile_year is not None:
        params["cover_year"] = profile_year
    return params


def _print_issue(issue: object) -> None:
    issue_series = getattr(issue, "series", None)
    issue_series_repr = (
        getattr(issue_series, "name", "?") if issue_series is not None else "?"
    )
    cover_date = getattr(issue, "cover_date", None)
    print(  # noqa: T201
        f"      id={issue.id} series={issue_series_repr!r} "  # type: ignore[attr-defined]
        f"number={getattr(issue, 'number', '?')!r} "
        f"cover_date={cover_date}"
    )


def _probe_issues_list(
    session: object, profile: object, series_results: list[object]
) -> None:
    """For each matching series, issue the production issues_list call."""
    for r in series_results:
        series_id = getattr(r, "id", None)
        if series_id is None:
            continue
        params = _build_issues_list_params(profile, series_id)
        print(f"\n  [follow-up] issues_list(params={params!r})")  # noqa: T201
        try:
            issues = list(session.issues_list(params=params))  # type: ignore[attr-defined]
        except Exception as exc:
            print(f"    EXCEPTION: {exc!r}")  # noqa: T201
            continue
        print(f"    → {len(issues)} result(s)")  # noqa: T201
        for issue in issues[:5]:
            _print_issue(issue)


def _debug_metron(profile: object, online: object) -> None:
    print("\n=== Metron debug ===")  # noqa: T201
    creds = online.sources.get("metron")  # type: ignore[attr-defined]
    if creds is None or not creds.username or not creds.password:
        print("  metron not configured; skipping")  # noqa: T201
        return
    src = MetronOnlineSource(creds, online)  # type: ignore[arg-type]
    session = src._get_session()
    series_name = profile.series  # type: ignore[attr-defined]

    # 1. Exactly what production sends.
    print(f"\n  [as-is] series_list(name={series_name!r})")  # noqa: T201
    try:
        results = list(session.series_list(params={"name": series_name}))
    except Exception as exc:
        print(f"    EXCEPTION: {exc!r}")  # noqa: T201
        return
    print(f"    → {len(results)} result(s)")  # noqa: T201
    for r in results[:5]:
        display = getattr(r, "display_name", None) or getattr(r, "name", "?")
        year = getattr(r, "year_began", "?")
        print(f"      id={r.id} {display!r} year_began={year}")  # noqa: T201

    # 1b. The actual second-step issues_list per matching series — production's
    # next call. Surfaces "series_list found AR but issues_list returned NM"
    # bugs.
    _probe_issues_list(session, profile, results[:5])

    # 2. Variant: word-by-word, dropping parens etc.
    cleaned = _clean_for_search(series_name)
    if cleaned and cleaned != series_name:
        print(f"\n  [cleaned] series_list(name={cleaned!r})")  # noqa: T201
        results2 = list(session.series_list(params={"name": cleaned}))
        print(f"    → {len(results2)} result(s)")  # noqa: T201
        for r in results2[:5]:
            display = getattr(r, "display_name", None) or getattr(r, "name", "?")
            year = getattr(r, "year_began", "?")
            print(f"      id={r.id} {display!r} year_began={year}")  # noqa: T201

    # 3. Variant: just first two words.
    words = (series_name or "").split()
    if len(words) >= 2:
        short = " ".join(words[:2])
        if short != cleaned:
            print(f"\n  [first-2-words] series_list(name={short!r})")  # noqa: T201
            results3 = list(session.series_list(params={"name": short}))
            print(f"    → {len(results3)} result(s)")  # noqa: T201
            for r in results3[:5]:
                display = getattr(r, "display_name", None) or getattr(r, "name", "?")
                year = getattr(r, "year_began", "?")
                print(f"      id={r.id} {display!r} year_began={year}")  # noqa: T201


def _debug_comicvine(profile: object, online: object) -> None:
    print("\n=== ComicVine debug ===")  # noqa: T201
    creds = online.sources.get("comicvine")  # type: ignore[attr-defined]
    if creds is None or not creds.api_key:
        print("  comicvine not configured; skipping")  # noqa: T201
        return
    from simyan.comicvine import ComicvineResource

    src = ComicVineOnlineSource(creds, online)  # type: ignore[arg-type]
    session = src._get_session()
    series_name = profile.series  # type: ignore[attr-defined]

    print(f"\n  [as-is] search(VOLUME, query={series_name!r}, max_results=20)")  # noqa: T201
    try:
        results = list(
            session.search(
                resource=ComicvineResource.VOLUME, query=series_name, max_results=20
            )
        )
    except Exception as exc:
        print(f"    EXCEPTION: {exc!r}")  # noqa: T201
        return
    print(f"    → {len(results)} volume(s)")  # noqa: T201
    for v in results[:5]:
        print(f"      id={v.id} name={v.name!r}")  # noqa: T201

    cleaned = _clean_for_search(series_name)
    if cleaned and cleaned != series_name:
        print(f"\n  [cleaned] search(VOLUME, query={cleaned!r}, max_results=20)")  # noqa: T201
        results2 = list(
            session.search(
                resource=ComicvineResource.VOLUME, query=cleaned, max_results=20
            )
        )
        print(f"    → {len(results2)} volume(s)")  # noqa: T201
        for v in results2[:5]:
            print(f"      id={v.id} name={v.name!r}")  # noqa: T201


def _clean_for_search(s: str | None) -> str:
    """Strip parens-and-contents, collapse whitespace."""
    if not s:
        return ""
    import re

    cleaned = re.sub(r"\([^)]*\)", "", s)  # strip "(...)"
    return re.sub(r"\s+", " ", cleaned).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("comic", type=Path, help="Path to the comic file")
    parser.add_argument(
        "--source",
        choices=("metron", "comicvine", "both"),
        default="both",
        help="Which source(s) to probe.",
    )
    args = parser.parse_args()

    comic = args.comic.expanduser()
    if not comic.exists():
        sys.stderr.write(f"{comic}: not found\n")
        return 1

    profile = _print_profile(comic)
    cfg = get_config(None)

    if args.source in ("metron", "both"):
        _debug_metron(profile, cfg.online)
    if args.source in ("comicvine", "both"):
        _debug_comicvine(profile, cfg.online)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
