"""
Cover-hash resources for online matching.

The matcher scores a candidate partly on how close its cover looks to the
comic's own, which needs two things a `Comicbox` has to own for its whole
lifetime: a sqlite cache of URL to perceptual hash, and a bounded HTTP
pool to fetch the covers that miss it. Both are expensive to build and
must be closed, so they live on the box rather than being rebuilt per
candidate.

Split out of `online_lookup` because the dependency runs one way — the
lookup flow reaches down here for a hash and nothing here calls back — and
because `close()` belongs with the resources it releases.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger
from typing_extensions import override

from comicbox.box.normalize import ComicboxNormalize

if TYPE_CHECKING:
    from collections.abc import Sequence

    from comicbox.formats.base.online.cover_hash import (
        CoverFetchPool,
        CoverHashUrlCache,
    )


class ComicboxOnlineCovers(ComicboxNormalize):
    """Owns the box-lifetime cover-hash cache and download pool."""

    # Lazily built, released by `close`. Declared here rather than in
    # __init__ because the box's mixin chain shares one constructor.
    _cover_hash_url_cache: CoverHashUrlCache | None = None
    _cover_fetch_pool: CoverFetchPool | None = None
    _local_cover_phash_computed: bool = False
    _local_cover_phash_value: str | None = None

    def _get_cover_hash_cache(self) -> CoverHashUrlCache | None:
        """
        Lazily open the shared cover-hash sqlite cache; None when caching is OFF.

        One connection for the box's lifetime (see `CoverHashUrlCache`),
        so a top-K batch costs one query in and one transaction out
        instead of two connections per candidate.
        """
        from comicbox.config.online.settings import CacheMode

        if self._config.online.cache.mode is CacheMode.OFF:
            return None
        if self._cover_hash_url_cache is None:
            from comicbox.formats.base.online.cover_hash import CoverHashUrlCache

            cache_dir = self._config.online.cache.dir
            if cache_dir is None:
                from platformdirs import user_cache_path

                cache_dir = user_cache_path("comicbox") / "online"
            cache_dir.mkdir(parents=True, exist_ok=True)
            self._cover_hash_url_cache = CoverHashUrlCache(
                cache_dir / "cover_hashes.sqlite"
            )
        return self._cover_hash_url_cache

    def _get_cover_fetch_pool(self) -> CoverFetchPool:
        """Lazily build the bounded download pool; one httpx client per box."""
        if self._cover_fetch_pool is None:
            from comicbox.formats.base.online.cover_hash import CoverFetchPool

            self._cover_fetch_pool = CoverFetchPool()
        return self._cover_fetch_pool

    def _candidate_cover_hash_batch_fetcher(
        self, urls: Sequence[str]
    ) -> dict[str, str]:
        """
        Resolve many candidate cover URLs to pHashes in one pass.

        Used by the matcher for sources that don't ship a precomputed
        hash (ComicVine, GCD). Cache lookups collapse into a single
        query; the remaining misses download concurrently over one
        shared HTTP client and are written back in one transaction.
        URLs that fail to download or hash are simply absent from the
        result — the matcher reads that as "no cover signal".
        """
        wanted = [u for u in dict.fromkeys(urls) if u]
        if not wanted:
            return {}
        cache = self._get_cover_hash_cache()
        resolved = cache.get_many(wanted) if cache is not None else {}
        missing = [u for u in wanted if u not in resolved]
        if not missing:
            return resolved
        fetched = self._get_cover_fetch_pool().fetch_hashes(missing)
        if cache is not None and fetched:
            cache.set_many(fetched.items())
        resolved.update(fetched)
        return resolved

    def _candidate_cover_hash_fetcher(self, url: str) -> str | None:
        """
        Download a candidate cover from URL and return its pHash, with caching.

        The single-URL entry point, kept for callers that resolve one
        candidate at a time; the matcher's hot path goes through
        `_candidate_cover_hash_batch_fetcher` instead.
        """
        if not url:
            return None
        return self._candidate_cover_hash_batch_fetcher((url,)).get(url)

    def _close_cover_hash_resources(self) -> None:
        """Release the cover-hash sqlite connection and HTTP client."""
        if self._cover_hash_url_cache is not None:
            self._cover_hash_url_cache.close()
            self._cover_hash_url_cache = None
        if self._cover_fetch_pool is not None:
            self._cover_fetch_pool.close()
            self._cover_fetch_pool = None

    @override
    def close(self) -> None:
        """Close the archive, then release online-lookup resources."""
        try:
            super().close()
        finally:
            self._close_cover_hash_resources()

    def _local_cover_phash(self) -> str | None:
        """Compute the comic's pHash on demand, cached on the box instance."""
        if self._local_cover_phash_computed:
            return self._local_cover_phash_value
        self._local_cover_phash_computed = True
        try:
            cover_bytes = self.get_cover_page(pdf_format="pixmap", skip_metadata=True)  # pyright: ignore[reportAttributeAccessIssue], # ty: ignore[unresolved-attribute]
        except Exception as exc:
            logger.debug(f"local cover: fetch failed: {exc}")
            return None
        if not cover_bytes:
            return None
        try:
            from comicbox.formats.base.online.cover_hash import compute_phash

            self._local_cover_phash_value = compute_phash(cover_bytes)
        except Exception as exc:
            logger.warning(f"local cover: pHash failed: {exc}")
        return self._local_cover_phash_value
