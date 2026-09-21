"""Lifecycle helpers for real upstream API clients built in tests."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path


def close_comicvine_client(client: Any) -> None:
    """
    Release every sqlite connection a simyan `Comicvine` opened.

    Delegates to the production close rather than keeping a second copy
    of the bucket dance it has to do.
    """
    from comicbox.formats.comicvine_api.online_source import close_client

    close_client(client)


def build_comicvine_client(cache_dir: Path, api_key: str = "k") -> Any:
    """
    Build a real `Comicvine` pointed at `cache_dir`.

    Its file names match what `ComicVineOnlineSource` would choose, so a
    status read against the same directory finds them.
    """
    from simyan.comicvine import Comicvine

    cache_dir.mkdir(parents=True, exist_ok=True)
    return Comicvine(
        api_key=api_key,
        cache_path=cache_dir / "comicvine_cache.sqlite",
        ratelimit_path=cache_dir / "comicvine_rate_limit.sqlite",
    )


@contextmanager
def comicvine_client(cache_dir: Path, api_key: str = "k") -> Generator[Any]:
    """Yield a real `Comicvine` pointed at `cache_dir`, fully closed on exit."""
    client = build_comicvine_client(cache_dir, api_key)
    try:
        yield client
    finally:
        close_comicvine_client(client)


def spend(client: Any, pool: str, times: int) -> None:
    """Claim `times` slots in a limiter pool via pyrate-limiter's public API."""
    limiter = client._session.limiter
    for _ in range(times):
        limiter.try_acquire(pool, weight=1, blocking=True, timeout=5)
