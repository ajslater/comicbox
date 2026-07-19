"""
ComicVine API source via simyan.

Wraps simyan's `Comicvine` client. simyan 3.x manages its own response
cache (requests_cache; `api_key` stripped from cache keys) and rate
limiting (1/sec, 200/hr in per-endpoint buckets) with a *bounded*
blocking wait (`max_delay = timeout * 2`); waits past that bound surface
as errors that comicbox's logged, cancellable retry layer handles. We
point the cache and rate-limit bucket files into comicbox's cache dir
via `online.cache_dir` / `cache_ttl`.

ComicVine candidates do *not* arrive with a precomputed cover hash, so
the matcher's hashing path downloads the candidate's `image.thumbnail`
when needed. Downloaded hashes are cached in
`${cache_dir}/cover_hashes.sqlite` keyed by URL.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import closing, suppress
from typing import TYPE_CHECKING, Any, ClassVar

from loguru import logger
from typing_extensions import override

from comicbox.formats import MetadataFormats
from comicbox.formats.base.online.profile import (
    Candidate,
    CandidateSummary,
    strip_issue_leading_zeros,
)
from comicbox.formats.base.online.retry import with_retry
from comicbox.formats.base.online.series_filter import (
    should_keep_volume_name,
)
from comicbox.formats.base.online.sources.base import (
    OnlineSource,
)
from comicbox.formats.base.online.warn_once import warn_once
from comicbox.formats.sources import MetadataSources
from comicbox.version import USER_AGENT

if TYPE_CHECKING:
    from datetime import timedelta
    from pathlib import Path

    from simyan.comicvine import Comicvine

    from comicbox.formats.base.online.profile import ComicProfile

# Cache files already housekept this process; sources (and thus clients)
# are rebuilt per file, and re-running the same purge/drop/vacuum SQL for
# every file of a batch would be pure overhead.
_maintained_cache_paths: set[str] = set()
_maintenance_lock = threading.Lock()


def _drop_v2_cache_table(cache_path: Path) -> None:
    """
    Drop simyan v2's `queries` table from the shared cache file.

    simyan 3.x (requests_cache) creates its own tables alongside; the old
    blob rows would otherwise sit as dead weight forever. A no-op once
    dropped. Best-effort — a locked/busy db just skips until next build.
    """
    with (
        suppress(sqlite3.Error),
        closing(sqlite3.connect(cache_path, isolation_level=None)) as conn,
    ):
        conn.execute("DROP TABLE IF EXISTS queries")


class ComicVineOnlineSource(OnlineSource):
    """Wraps simyan for the ComicVine API."""

    name: ClassVar[str] = "comicvine"
    metadata_source: ClassVar[MetadataSources] = MetadataSources.COMICVINE_API
    metadata_format: ClassVar[MetadataFormats] = MetadataFormats.COMICVINE_API

    @override
    def is_configured(self) -> bool:
        """ComicVine requires an api_key."""
        return bool(self._credentials.key)

    def _get_session(self) -> Comicvine:
        """Build the simyan client once per source lifetime, then reuse it."""
        if self._client is None:
            self._client = self._build_session()
        return self._client

    def _build_session(self) -> Comicvine:
        from simyan.comicvine import Comicvine

        self._warn_ignored_rate_limit_overrides()
        # Both paths are always passed explicitly — simyan's defaults land
        # in ~/.cache/simyan, outside comicbox's cache dir.
        cache_path = self.cache_db_path()
        resolved = self._resolve_response_cache()  # REFRESH unlinks in here
        kwargs: dict[str, Any] = {
            "api_key": self._credentials.key,
            "user_agent": USER_AGENT,
            "cache_path": cache_path,
            "cache_expiry": self._cache_expiry(resolved),
            "ratelimit_path": self.cache_db_path("rate_limit"),
        }
        if self._credentials.url:
            kwargs["base_url"] = self._credentials.url
        client = Comicvine(**kwargs)
        if resolved is None:  # CacheMode.OFF
            self._disable_response_cache(client)
        else:
            self._maintain_cache(client, cache_path)
        return client

    @staticmethod
    def _cache_expiry(resolved: tuple[Path, timedelta] | None) -> Any:
        """Map comicbox's resolved cache mode/ttl onto simyan's `cache_expiry`."""
        from requests_cache import DO_NOT_CACHE, NEVER_EXPIRE

        if resolved is None:  # CacheMode.OFF
            return DO_NOT_CACHE
        _, ttl = resolved
        return ttl if ttl.total_seconds() > 0 else NEVER_EXPIRE

    def _disable_response_cache(self, client: Comicvine) -> None:
        """
        Make CacheMode.OFF mean no cache reads AND no cache writes.

        `DO_NOT_CACHE` alone skips reads, but simyan enables
        `cache_control`, which lets a response carrying explicit cache
        headers re-derive an expiry and get written anyway. The settings
        flag turns the session into a plain requests one. Best-effort
        private reach-in; `DO_NOT_CACHE` remains as the fallback signal.
        """
        try:
            client._session.settings.disabled = True  # noqa: SLF001
        except Exception as exc:
            logger.debug(f"online {self.name}: cache disable skipped: {exc}")

    def _warn_ignored_rate_limit_overrides(self) -> None:
        from comicbox.config.settings import resolve_rate_limit

        limits = resolve_rate_limit(self._settings, self.name)
        if limits.per_second is not None or limits.per_hour is not None:
            # Sources are rebuilt per file; warn_once keeps this at one
            # line per process instead of one per file in a batch run.
            warn_once(
                f"{self.name}:rate-limit-override",
                f"online {self.name}: rate_limit.per_second/per_hour "
                "overrides are ignored — simyan 3.x manages ComicVine "
                "rates internally (1/sec, 200/hr)",
            )

    def _maintain_cache(self, client: Comicvine, cache_path: Path) -> None:
        """
        Purge expired rows, drop the v2 table, and vacuum if bloated.

        requests_cache never deletes expired rows on its own (simyan v2's
        cache did, on open) — without the purge the freelist-based vacuum
        trigger would rarely fire and the cache would grow unbounded.
        Runs once per process per cache file.
        """
        from comicbox.formats.base.online.vacuum import vacuum_if_bloated

        if not cache_path.exists():
            return
        with _maintenance_lock:
            if str(cache_path) in _maintained_cache_paths:
                return
            _maintained_cache_paths.add(str(cache_path))
        try:
            # The session and its cache are private simyan surface (typed
            # Any accordingly); degrade to "no purge" on a rename.
            cache: Any = client._session.cache  # noqa: SLF001
            # vacuum=False: requests_cache's SQLite backend would otherwise
            # rewrite the whole file on every purge; vacuum_if_bloated below
            # only does so when the freelist justifies it.
            cache.delete(expired=True, vacuum=False)
        except Exception as exc:
            logger.debug(f"online {self.name}: cache purge skipped: {exc}")
        _drop_v2_cache_table(cache_path)
        vacuum_if_bloated(cache_path)

    @with_retry()
    def get(self, issue_id: int) -> dict[str, Any]:
        """
        Fetch one ComicVine issue by id; return its model dump.

        CV's issue endpoint does NOT include the publisher inline —
        `Issue.volume` is a bare `GenericEntry`. We chase one extra
        request to ``get_volume(volume.id)`` to pull
        ``Volume.publisher`` and inject it under a top-level ``publisher``
        key for the transform to pick up. simyan's response cache is
        URL-keyed, so this is "+1 API call per unique volume" rather
        than per issue — successive issues from the same volume are free.
        """
        session = self._get_session()
        self._record_api_call("get_issue")
        issue = session.get_issue(issue_id)
        dump: dict[str, Any] = issue.model_dump(mode="json")
        # `issue.volume` is a GenericEntry with id; fetch the full volume
        # to get its publisher. Best-effort — log and continue on failure.
        volume_id = (issue.volume.id if issue.volume else None) or (
            (dump.get("volume") or {}).get("id")
        )
        if volume_id is not None:
            try:
                volume = self._get_volume_with_retry(session, int(volume_id))
            except Exception as exc:
                logger.warning(
                    f"online {self.name}: get_volume({volume_id}) failed; "
                    f"publisher will be missing from this issue: {exc}"
                )
            else:
                if volume.publisher is not None:
                    dump["publisher"] = volume.publisher.model_dump(mode="json")
        return dump

    # Limit how many candidate volumes to expand into issue queries; each
    # volume → one extra `list_issues` API call under CV's 1/sec rate limit.
    _MAX_VOLUMES_PER_SEARCH: ClassVar[int] = 20

    # ComicVine `Images` field names from smallest to largest.
    # `thumbnail` is sufficient for pHash; the rest are fallbacks for
    # records where a particular size is missing.
    _COVER_URL_PREFERENCE: ClassVar[tuple[str, ...]] = (
        "thumbnail",
        "small_url",
        "medium_url",
        "screen_url",
        "super_url",
        "original_url",
    )

    @classmethod
    def _pick_cover_url(cls, image: Any) -> str | None:
        if image is None:
            return None
        for attr in cls._COVER_URL_PREFERENCE:
            url = getattr(image, attr, None)
            if url:
                return str(url)
        return None

    def _to_candidate(
        self, basic_issue: Any, volume_name: str | None = None
    ) -> Candidate:
        """
        Map simyan's `BasicIssue` to a Candidate.

        ``volume_name`` overrides the series field when supplied — the
        two-step search has already resolved the volume so we use its
        canonical name even if `basic_issue.volume.name` is sparse.
        """
        bi_volume = basic_issue.volume
        series = volume_name or (bi_volume.name if bi_volume else "") or ""
        cover_year = basic_issue.cover_date.year if basic_issue.cover_date else None
        cover_url = self._pick_cover_url(basic_issue.image)
        site_url = str(basic_issue.site_url) if basic_issue.site_url else ""
        summary = CandidateSummary(
            series=series,
            issue=basic_issue.number or "",
            year=cover_year,
            publisher=None,  # BasicIssue from search doesn't include publisher
            page_count=None,
            cover_url=cover_url,
            variant_label=None,
        )
        return Candidate(
            source=self.name,
            issue_id=basic_issue.id,
            summary=summary,
            url=site_url,
            # ComicVine doesn't expose a precomputed pHash; matcher will
            # download and hash on demand if needed.
            precomputed_cover_hash=None,
            # CV's volume.id — propagated for calibration diagnostics
            # (lets us tell "variant cover of same volume" apart from
            # "wrong volume with the same name" when two candidates tie).
            volume_id=bi_volume.id if bi_volume else None,
        )

    # Cover-date window applied around `profile.year` when filtering
    # CV's per-volume issue lookup. ±2 years gives the year-only matcher
    # a small slop budget without admitting wholly-wrong-volume matches
    # that score well on every other signal.
    _COVER_DATE_WINDOW_YEARS: ClassVar[int] = 2

    # Maximum number of years a comic may pre-date its volume's start_year
    # before we treat the volume as causally impossible and skip the
    # per-volume issue lookup. A 1987 Watchmen issue with profile.year=1987
    # cannot have been published in a reprint volume that started in 2008;
    # any candidate from that volume is a reprint with cover_date=1987
    # preserved from the original, score-identical to the original on
    # every signal the matcher reads. Skip-and-save-budget is cleaner
    # than admitting the candidate and hoping a tiebreaker resolves it.
    #
    # The slop=1 matches `s_year`'s diff=1 tolerance — we accept "started
    # the year after the comic's cover date" cases (off-by-one cover
    # dating across publisher fiscal year boundaries) without keeping
    # outright impossible volumes.
    _VOLUME_START_YEAR_SLOP: ClassVar[int] = 1

    @with_retry()
    def _get_volume_with_retry(self, session: Any, volume_id: int) -> Any:
        """
        Per-call retry wrapper around `session.get_volume`.

        This is the supplementary publisher-lookup call in `get()`. The
        outer `get()` is itself `@with_retry()`-decorated but its inner
        `try/except` swallows rate-limit errors as "best effort" —
        meaning under -j N contention every transient rate-limit on
        get_volume silently drops the publisher field. Wrapping the
        call here lets rate-limit hits replay transparently; the outer
        except only catches terminal failures (404, retries exhausted).
        """
        self._record_api_call("get_volume")
        return session.get_volume(volume_id)

    def _discover_volumes(
        self, session: Any, profile: ComicProfile, max_volumes: int
    ) -> list[Any]:
        """
        Union-of-narrow-and-fuzzy volume discovery.

        Always runs both:
        - Fuzzy `session.search(VOLUME, query)` — CV's text-relevance
          ranking. Surfaces canonical / popular volumes.
        - Narrow `session.list_volumes(name+start_year filter)` — only
          when profile.year is set. Surfaces the specific year's volume
          for Pattern A cases (reissues, trade collections, facsimiles)
          where CV's relevance buries the year-anchored volume below
          older canonical runs.

        Results are dedup'd by volume_id (fuzzy order preserved first;
        narrow's new entries appended). Both halves are independently
        capped at ``max_volumes``; the union is capped at
        ``2 * max_volumes``.

        Replaces the 2026-05-17 narrow-then-fuzzy approach which lost
        previously-correct fuzzy candidates whenever the narrow filter
        returned a wrong volume. Union preserves fuzzy's candidates so
        the matcher still scores them; narrow's contribution is purely
        additive.
        """
        # Fuzzy always runs (preserves today's behaviour as a floor).
        try:
            fuzzy = self._volume_search_with_retry(session, profile.series, max_volumes)
        except Exception as exc:
            logger.warning(f"online {self.name}: volume search failed: {exc}")
            raise

        if profile.year is None:
            return fuzzy

        try:
            narrow = self._volume_filter_search_with_retry(
                session, profile.series, profile.year, max_volumes
            )
        except Exception as exc:
            logger.info(
                f"online {self.name}: volume filter-search failed "
                f"({exc}); proceeding with fuzzy-only candidates"
            )
            return fuzzy

        if not narrow:
            return fuzzy

        # Dedup union, fuzzy first to preserve relevance ordering for
        # already-good cases. Narrow's new entries appended.
        fuzzy_ids = {v.id for v in fuzzy}
        narrow_only = [v for v in narrow if v.id not in fuzzy_ids]
        if narrow_only:
            logger.debug(
                f"online {self.name}: narrow filter added "
                f"{len(narrow_only)} volume(s) to fuzzy's {len(fuzzy)} "
                f"for series={profile.series!r} start_year={profile.year}"
            )
        return fuzzy + narrow_only

    @with_retry()
    def _volume_search_with_retry(
        self, session: Any, query: str, max_results: int
    ) -> list[Any]:
        """
        Per-call retry wrapper around `session.search(VOLUME, ...)`.

        Mirrors the Metron `_series_list_with_retry` fix from the same
        2026-05-15-stress-100 audit pass: the volume-search call was
        un-retried, so under -j N contention a single rate-limit hit
        would drop the entire fixture's candidate set instead of
        retrying transparently.
        """
        from simyan.comicvine import ComicvineResource

        self._record_api_call("search_volumes")
        return session.search(
            resource=ComicvineResource.VOLUME,
            query=query,
            max_results=max_results,
        )

    @with_retry()
    def _volume_filter_search_with_retry(
        self, session: Any, query: str, start_year: int, max_results: int
    ) -> list[Any]:
        """
        Narrow volume search via `list_volumes` server-side filter.

        Uses CV's `/volumes` endpoint with `name:<query>,start_year:<year>`
        filter — different code path from the fuzzy `/search` endpoint.
        Always paired with fuzzy via ``_discover_volumes``; never used
        as a replacement. See that method's docstring + the failure
        history in
        ``tasks/online-tagging/research-notes/cv-top-5-search-relevance.md``.
        """
        self._record_api_call("filter_volumes")
        # CV's filter syntax: `field1:value1,field2:value2`. Commas and
        # colons in the query would break the parser. Strip them — they're
        # rare in series names and won't affect icontains matching.
        safe_query = query.replace(",", " ").replace(":", " ").strip()
        return session.list_volumes(
            params={"filter": f"name:{safe_query},start_year:{start_year}"},
            max_results=max_results,
        )

    @override
    def _lookup_issue_in_volume(
        self, volume_id: int, issue_number: str | None
    ) -> Candidate | None:
        """
        Volume-scoped issue lookup; cheaper than the fuzzy search path.

        One ``list_issues`` call filtered by ``volume:`` + ``issue_number:``.
        The base class's ``lookup_issue`` wrapper owns the failure
        semantics (plan §3.10).
        """
        session = self._get_session()
        candidates = self._list_issues_by_volume(session, volume_id, issue_number)
        if not candidates:
            return None
        # First-result-wins on variant collisions; same approach as Metron.
        return candidates[0]

    @with_retry()
    def _list_issues_by_volume(
        self,
        session: Any,
        volume_id: int,
        issue_number: str | None,
        volume_name: str | None = None,
        *,
        year: int | None = None,
    ) -> list[Candidate]:
        """
        Run a single ``list_issues`` call constrained by volume id.

        Used both by the fast path (`--series-id comicvine:<id>`) and by
        each iteration of the discovery two-step. ``volume_name`` is set
        on the returned candidates' summary when available.

        ``year``, when supplied, narrows results to a ±_COVER_DATE_WINDOW_YEARS
        window around it via CV's ``cover_date:Y0-01-01|Y1-12-31``
        filter syntax. Cover-date drift is rarely more than ±1 year so a
        2-year slop is generous; this prevents wrong-volume picks (e.g.
        a 1986 series matching a 2005 collected edition with the same
        issue number) from polluting the candidate set in the first place.

        Decorated with ``@with_retry()`` so a rate-limit hit on this
        single call waits out the rate-limit backoff schedule and replays
        just the failed call. The outer ``search`` loop catches and continues
        on the FINAL failure after retries are exhausted, so transient
        rate-limit hits inside the loop no longer silently drop the
        per-volume issue data.
        """
        self._record_api_call("list_issues")
        issue_filter = [f"volume:{volume_id}"]
        if issue_number:
            issue_filter.append(f"issue_number:{issue_number}")
        if year is not None:
            window = self._COVER_DATE_WINDOW_YEARS
            issue_filter.append(
                f"cover_date:{year - window}-01-01|{year + window}-12-31"
            )
        issues = session.list_issues(params={"filter": ",".join(issue_filter)})
        return [self._to_candidate(i, volume_name) for i in issues]

    def _volume_predates_comic(
        self, vol_start_year: int | None, comic_year: int | None
    ) -> bool:
        """
        Return True when the volume started so far after the comic to be impossible.

        Used to skip per-volume issue queries for volumes whose `start_year`
        is later than the comic year + slop. Reprint volumes (which copy the
        original's cover_date onto their issues) are score-identical to
        the original on every signal the matcher reads — the only thing
        that distinguishes them is their volume start_year, and the
        matcher doesn't see that. Filtering at search time avoids both
        wrong-volume picks and the wasted `list_issues` call.

        Returns False (i.e. keep the volume) when either input is None —
        we'd rather over-include than drop the right answer on missing
        data.
        """
        if vol_start_year is None or comic_year is None:
            return False
        return vol_start_year > comic_year + self._VOLUME_START_YEAR_SLOP

    @override
    def search(self, profile: ComicProfile) -> list[Candidate]:
        """
        Search ComicVine for candidate issues matching the profile.

        ComicVine's ``list_issues`` filter has no series/volume-name field —
        its `name:` filter matches the *issue's* title, which is rarely
        useful. So we do the canonical two-step:

        1. Full-text-search for volumes matching the series name. (The
           ``list_volumes`` filter `name:` is strict and trips on
           punctuation: "GI Joe" vs "G.I. Joe". Full-text search is
           more permissive.)
        2. For each volume, ``list_issues`` filtered by ``volume:VOL_ID``
           and ``issue_number:N`` → candidate issues for that volume.

        ``--series-id comicvine:<id>`` short-circuits step 1 and runs
        only step 2 against the supplied volume id.

        Volumes whose ``start_year`` is *later* than ``profile.year + 1``
        (causally impossible — a reprint volume started in 2008 cannot
        contain the original 1987 issue) are dropped before step 2;
        otherwise ``start_year`` is NOT used as a filter, since a comic
        dated 2020 can legitimately be issue #100 of a series that
        started in 1963. ``profile.year`` is also used as a per-issue
        ``cover_date`` window (±2 years) inside step 2, to keep
        wrong-volume candidates with the same issue number out of the
        candidate set entirely. If that year filter returns empty (CV
        has issues with missing cover_date), we retry once without it.
        """
        session = self._get_session()
        issue_number = strip_issue_leading_zeros(profile.issue)
        year = profile.year
        # Fast path: --series-id comicvine:<id> skips the volume search and
        # goes straight to a single list_issues call constrained by that
        # volume id, saving the discovery API call.
        explicit_sid = self._settings.lookup.series_ids.get(self.name)
        if explicit_sid is not None:
            try:
                return self._list_with_year_retry(
                    session, explicit_sid, issue_number, None, year=year
                )
            except Exception as exc:
                logger.warning(
                    f"online {self.name}: issue-list for volume {explicit_sid} "
                    f"failed: {exc}"
                )
                raise

        if not profile.series:
            logger.debug(
                f"online {self.name}: no series in profile; cannot search CV "
                "(use --id comicvine:<id> for direct lookup, or "
                "--series-id comicvine:<id>)"
            )
            return []

        # Phase D: `fast` budget caps the volume-search breadth more
        # aggressively than the class default (20 → 5). Cuts the per-volume
        # `list_issues` fan-out further at scale; the pre-filter already
        # drops obvious mismatches but the long tail of weakly-matching
        # volumes adds up across thousands of comics.
        max_volumes = self._effort_max_results(self._MAX_VOLUMES_PER_SEARCH)
        volumes = self._discover_volumes(session, profile, max_volumes)
        if not volumes:
            logger.info(
                f"online {self.name}: no volumes match series {profile.series!r}"
            )
            return []
        self._log_discovery_sample(
            volumes,
            lambda v: f"{v.name} ({v.id})",
            noun="volumes",
            query=f"series={profile.series!r}",
        )

        # Pre-call filter threshold from the resolved API budget. At the
        # `balanced` default this resolves to 0.0 (filter is a no-op), so
        # Phase A behaviour is identical to today's. Phase B calibration
        # picks the real values for `fast` (currently 0.7 placeholder).
        name_threshold = self._effort_name_threshold()

        candidates: list[Candidate] = []
        for vol in volumes:
            candidates.extend(
                self._candidates_for_volume(
                    session,
                    vol,
                    profile=profile,
                    issue_number=issue_number,
                    year=year,
                    name_threshold=name_threshold,
                )
            )
        return candidates

    def _candidates_for_volume(
        self,
        session: Any,
        vol: Any,
        *,
        profile: ComicProfile,
        issue_number: str | None,
        year: int | None,
        name_threshold: float,
    ) -> list[Candidate]:
        """
        Apply pre-call filters and (if kept) fetch the volume's matching issues.

        Pre-filters in order: start_year causality (skip volumes that
        started after the comic), then series-name fuzzy match (skip
        volumes whose name diverges from `profile.series` past the
        api_budget threshold). Both filters log at debug level so
        calibration runs can audit drops. The actual `list_issues` call
        only fires for volumes that survive both gates.
        """
        vol_start = getattr(vol, "start_year", None)
        if self._volume_predates_comic(vol_start, year):
            logger.debug(
                f"online {self.name}: skipping volume {vol.id} "
                f"({vol.name!r}, start_year={vol_start}); comic "
                f"year={year} predates the volume — issue cannot "
                f"originate here."
            )
            return []
        if not should_keep_volume_name(profile.series, vol.name, name_threshold):
            logger.debug(
                f"online {self.name}: skipping volume {vol.id} "
                f"({vol.name!r}); name dissimilar to "
                f"profile.series={profile.series!r} (threshold="
                f"{name_threshold:.2f}, api_budget pre-filter)."
            )
            return []
        try:
            return self._list_with_year_retry(
                session, vol.id, issue_number, vol.name, year=year
            )
        except Exception as exc:
            logger.warning(
                f"online {self.name}: issue-list for volume {vol.id} "
                f"({vol.name!r}) failed: {exc}"
            )
            return []

    def _list_with_year_retry(
        self,
        session: Any,
        volume_id: int,
        issue_number: str | None,
        volume_name: str | None,
        *,
        year: int | None,
    ) -> list[Candidate]:
        """
        Per-volume issue lookup with a year-window filter and one fallback.

        Tries `cover_date:Y±2` first (cuts out wrong-volume candidates).
        If that returns empty AND a year was supplied, retries without
        the year filter — cover_date can be missing on CV issues, and
        we'd rather see *something* and let the matcher score it than
        wrongly drop the right answer.
        """
        candidates = self._list_issues_by_volume(
            session, volume_id, issue_number, volume_name, year=year
        )
        if candidates or year is None:
            return candidates
        return self._list_issues_by_volume(
            session, volume_id, issue_number, volume_name, year=None
        )
