"""
Metron API source via mokkari.

M2 wires the `--id metron:N` path: instantiate a session with credentials
from the resolution chain, fetch one issue by id, dump the Pydantic model
to a plain dict, and hand it back to `ComicboxOnlineLookup` for transform
and merge. M3 adds search.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from loguru import logger

from comicbox.formats import MetadataFormats
from comicbox.online.profile import (
    Candidate,
    CandidateSummary,
    strip_issue_leading_zeros,
)
from comicbox.online.retry import with_retry
from comicbox.online.sources.base import OnlineSource
from comicbox.sources import MetadataSources
from comicbox.version import PACKAGE_NAME, VERSION

if TYPE_CHECKING:
    from mokkari.session import Session

    from comicbox.online.profile import ComicProfile


class MetronOnlineSource(OnlineSource):
    """Wraps mokkari for the Metron API."""

    name: ClassVar[str] = "metron"
    metadata_source: ClassVar[MetadataSources] = MetadataSources.METRON_API
    metadata_format: ClassVar[MetadataFormats] = MetadataFormats.METRON_API

    def is_configured(self) -> bool:
        """Metron requires both username and password."""
        return bool(self._credentials.username and self._credentials.password)

    def _get_cache(self) -> Any:
        if not self._settings.cache_enabled:
            return None
        from mokkari.sqlite_cache import SqliteCache

        cache_path = self.cache_db_path()
        if self._settings.refresh_cache and cache_path.exists():
            cache_path.unlink()
            logger.debug(f"refresh-cache: removed {cache_path}")
        ttl = self._settings.cache_ttl
        expire = int(ttl.total_seconds()) if ttl.total_seconds() > 0 else None
        return SqliteCache(db_name=str(cache_path), expire=expire)

    def _get_session(self) -> Session:
        from mokkari import api
        from mokkari.session import Session as _MokkariSession

        from comicbox.online.rate_limits import build_metron_bucket

        if self._credentials.url:
            # mokkari's api() factory has no URL-override parameter (only
            # dev_mode for the dev API), so --api-url metron:<url> can't
            # actually be honored. Warn so the user notices.
            logger.warning(
                f"online {self.name}: --api-url is a no-op for metron "
                f"(mokkari has no base_url override); ignoring "
                f"{self._credentials.url!r}"
            )
        bucket = build_metron_bucket(self._settings.source_limits.get(self.name))
        if bucket is None:
            # No override: defer to mokkari's default (a process-wide SQLite
            # bucket at the documented 20/min and 5,000/day limits).
            return api(
                username=self._credentials.username,
                passwd=self._credentials.password,
                cache=self._get_cache(),
                user_agent=f"{PACKAGE_NAME}/{VERSION}",
            )
        # Override: mokkari's `api()` factory doesn't expose `bucket`, so
        # construct the Session directly and pass our custom bucket.
        return _MokkariSession(
            username=self._credentials.username,
            passwd=self._credentials.password,
            cache=self._get_cache(),
            user_agent=f"{PACKAGE_NAME}/{VERSION}",
            bucket=bucket,
        )

    @with_retry()
    def get(self, issue_id: int) -> dict[str, Any]:
        """Fetch one Metron issue by id; return its model dump."""
        session = self._get_session()
        issue = session.issue(issue_id)
        return issue.model_dump(mode="json")

    # Limit how many candidate series to expand into issue queries; each
    # series → one extra `issues_list` API call.
    _MAX_SERIES_PER_SEARCH: ClassVar[int] = 20

    def _build_issue_params(
        self,
        profile: ComicProfile,
        series_id: int,
        *,
        cover_year_override: int | None = None,
        include_volume: bool = True,
    ) -> dict[str, Any]:
        """
        Build the `issues_list` params filtering on a resolved series id.

        ``cover_year_override`` lets the ±1 retry-on-miss path supply a
        neighboring year. When None, ``profile.year`` is used as-is.

        ``include_volume`` is the toggle for the drop-volume retry path:
        passing False omits Metron's ``series_volume`` filter even when
        ``profile.volume`` is set.
        """
        params: dict[str, Any] = {"series": series_id}
        # Strip leading zeros — Metron stores `number` without padding.
        if number := strip_issue_leading_zeros(profile.issue):
            params["number"] = number
        cover_year = (
            cover_year_override if cover_year_override is not None else profile.year
        )
        if cover_year is not None:
            params["cover_year"] = cover_year
        if include_volume and profile.volume is not None:
            params["series_volume"] = profile.volume
        return params

    def _to_candidate(
        self, base_issue: Any, series_name: str | None = None
    ) -> Candidate:
        """
        Map a mokkari `BaseIssue` to a Candidate.

        ``series_name`` overrides the issue's series field when supplied — the
        two-step search has already resolved the series so we use its
        canonical name, since `BaseIssue.series` is sparse.
        """
        cover_year = base_issue.cover_date.year if base_issue.cover_date else None
        image_url = str(base_issue.image) if base_issue.image else None
        # `BaseIssue.series` may be a nested object or absent depending on
        # the endpoint. Prefer the resolved name passed in by `search`.
        bi_series = getattr(base_issue, "series", None)
        series = (
            series_name
            or (getattr(bi_series, "name", None) if bi_series is not None else None)
            or ""
        )
        summary = CandidateSummary(
            series=series,
            issue=base_issue.number,
            year=cover_year,
            publisher=None,  # BaseIssue from search omits publisher
            page_count=None,
            cover_url=image_url,
            variant_label=None,
        )
        return Candidate(
            source=self.name,
            issue_id=base_issue.id,
            summary=summary,
            url=str(base_issue.resource_url)
            if hasattr(base_issue, "resource_url") and base_issue.resource_url
            else "",
            precomputed_cover_hash=getattr(base_issue, "cover_hash", None) or None,
        )

    @with_retry()
    def search(self, profile: ComicProfile) -> list[Candidate]:
        """
        Search Metron for candidate issues matching the profile.

        The canonical two-step:

        1. ``series_list({"name": profile.series})`` — Metron's name filter
           is icontains+unaccent and splits on whitespace (AND-of-terms),
           so it tolerates case, accents, and word-order quirks.
        2. For each matched series, ``issues_list({"series": id, "number":
           N, "cover_year": Y})`` — issue lookup constrained by the
           resolved series id. Metron's `issue.number` is unpadded, so we
           strip leading zeros on the way in.

        The earlier single-call form passed `series_name` directly to
        ``issues_list``, which Metron does accept (icontains too) but it's
        an undocumented mokkari parameter and the two-step is what
        metron-tagger uses.
        """
        session = self._get_session()
        # Fast path: --series-id metron:<id> skips the discovery call and goes
        # straight to issue lookup against the supplied series id. The series
        # name on candidates falls back to whatever `BaseIssue.series.name` we
        # get back; we don't pre-resolve it because that'd cost the call we
        # just saved.
        explicit_sid = self._settings.explicit_series_ids.get(self.name)
        if explicit_sid is not None:
            # The user has been explicit about the series id; the soft volume
            # filter would just risk false-zero. Trust the supplied id.
            params = self._build_issue_params(
                profile, explicit_sid, include_volume=False
            )
            try:
                issues = session.issues_list(params=params)
            except Exception as exc:
                logger.warning(
                    f"online {self.name}: issue-list for series id "
                    f"{explicit_sid} failed: {exc}"
                )
                raise
            return [self._to_candidate(i) for i in issues]

        if not profile.series:
            logger.debug(
                f"online {self.name}: no series in profile; cannot search Metron "
                "(use --id metron:<id> for direct lookup, or --series-id metron:<id>)"
            )
            return []
        try:
            series_results = session.series_list(params={"name": profile.series})
        except Exception as exc:
            logger.warning(f"online {self.name}: series search failed: {exc}")
            raise
        if not series_results:
            logger.info(f"online {self.name}: no series match {profile.series!r}")
            return []
        series_results = list(series_results)[: self._MAX_SERIES_PER_SEARCH]
        sample_size = 5
        sample = ", ".join(
            f"{_series_display_name(s)} ({s.id})" for s in series_results[:sample_size]
        )
        if len(series_results) > sample_size:
            sample += " ..."
        logger.debug(
            f"online {self.name}: {len(series_results)} candidate series for "
            f"{profile.series!r}: {sample}"
        )

        candidates = self._search_with_year_retry(
            session, profile, series_results, include_volume=True
        )

        # Drop-volume retry on miss. Filename-parsed `Vol. N` is moderately
        # reliable but inconsistent — some scanners drop it, some get the
        # number wrong. If the volume-filtered cycle (year-exact + Y±1)
        # returned nothing, retry the whole cycle without the volume
        # filter. Skipped if no volume was filtering in the first place.
        if not candidates and profile.volume is not None:
            logger.info(
                f"online {self.name}: 0 candidates with series_volume="
                f"{profile.volume}, retrying without the volume filter"
            )
            candidates = self._search_with_year_retry(
                session, profile, series_results, include_volume=False
            )

        return candidates

    def _search_with_year_retry(
        self,
        session: Session,
        profile: ComicProfile,
        series_results: list[Any],
        *,
        include_volume: bool,
    ) -> list[Candidate]:
        """
        Year-exact pass plus ±1 retry on miss; volume filter is optional.

        Cover-date drift is real: a comic published in late 2019 can be
        cover-dated 2020-01. When the year-exact pass returns zero, retry
        with Y-1 then Y+1. Skipped if there's no year to relax.
        """
        candidates = self._fetch_candidates_across_series(
            session,
            profile,
            series_results,
            cover_year_override=None,
            include_volume=include_volume,
        )
        if not candidates and profile.year is not None:
            for delta in (-1, 1):
                retry_year = profile.year + delta
                logger.info(
                    f"online {self.name}: 0 candidates at year={profile.year}, "
                    f"retrying with cover_year={retry_year}"
                )
                retry = self._fetch_candidates_across_series(
                    session,
                    profile,
                    series_results,
                    cover_year_override=retry_year,
                    include_volume=include_volume,
                )
                candidates.extend(retry)
        return candidates

    def _fetch_candidates_across_series(
        self,
        session: Session,
        profile: ComicProfile,
        series_results: list[Any],
        *,
        cover_year_override: int | None,
        include_volume: bool = True,
    ) -> list[Candidate]:
        """Run `issues_list` once per series, accumulating candidates."""
        candidates: list[Candidate] = []
        for series in series_results:
            display = _series_display_name(series)
            params = self._build_issue_params(
                profile,
                series.id,
                cover_year_override=cover_year_override,
                include_volume=include_volume,
            )
            try:
                issues = session.issues_list(params=params)
            except Exception as exc:
                logger.warning(
                    f"online {self.name}: issue-list for series {series.id} "
                    f"({display!r}) failed: {exc}"
                )
                continue
            candidates.extend(self._to_candidate(i, display) for i in issues)
        return candidates


def _series_display_name(series: Any) -> str:
    """
    Pull the human-readable name out of a mokkari series-shaped object.

    `BaseSeries` exposes `display_name` (alias from `series` in the JSON);
    full `Series` and our test fakes expose `name`. Prefer `display_name`
    so this works against the real `series_list` response while still
    accommodating either shape.
    """
    return getattr(series, "display_name", None) or getattr(series, "name", None) or ""
