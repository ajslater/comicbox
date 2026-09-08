"""
`--refresh-cache` unlink-once tests.

`refresh_cache_unlink_once` exists because REFRESH means "discard stale
state at run start", not "disable caching". Clients are rebuilt during a
run and sources are rebuilt per file, so an unguarded unlink wiped the
response cache *between* calls of the same file — defeating the
+1-API-call-per-unique-volume amortization `get()` relies on. These
tests pin the exact regression that docstring records.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from comicbox.formats.base.online.sources import base as sources_base

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture(autouse=True)
def _clean_registry() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Isolate the unlink-once registry, which is a module global."""
    saved = set(sources_base._refreshed_cache_paths)
    sources_base._refreshed_cache_paths.clear()
    try:
        yield
    finally:
        sources_base._refreshed_cache_paths.clear()
        sources_base._refreshed_cache_paths.update(saved)


def test_second_caller_in_the_same_process_does_not_unlink(tmp_path: Path) -> None:
    """The regression: a per-file source rebuild must not re-wipe the cache."""
    cache = tmp_path / "responses.sqlite"
    cache.write_text("stale from a previous run")

    sources_base.refresh_cache_unlink_once(cache)
    assert not cache.exists()

    # The run re-warms the cache; the next source's REFRESH is a no-op.
    cache.write_text("warmed by this run")
    sources_base.refresh_cache_unlink_once(cache)
    assert cache.read_text() == "warmed by this run"


def test_repeated_calls_stay_no_ops(tmp_path: Path) -> None:
    """Every later call in the process is a no-op, not just the second."""
    cache = tmp_path / "responses.sqlite"
    cache.write_text("stale")
    sources_base.refresh_cache_unlink_once(cache)
    cache.write_text("warm")
    for _ in range(5):
        sources_base.refresh_cache_unlink_once(cache)
    assert cache.read_text() == "warm"


def test_paths_are_tracked_independently(tmp_path: Path) -> None:
    """One source's unlink must not consume another source's one shot."""
    metron = tmp_path / "metron.sqlite"
    comicvine = tmp_path / "comicvine.sqlite"
    metron.write_text("stale")
    comicvine.write_text("stale")

    sources_base.refresh_cache_unlink_once(metron)
    assert not metron.exists()
    assert comicvine.exists()

    sources_base.refresh_cache_unlink_once(comicvine)
    assert not comicvine.exists()


def test_missing_file_still_burns_the_one_shot(tmp_path: Path) -> None:
    """A cold cache has nothing to unlink — and is still marked refreshed."""
    cache = tmp_path / "absent.sqlite"
    sources_base.refresh_cache_unlink_once(cache)
    assert not cache.exists()

    cache.write_text("warmed by this run")
    sources_base.refresh_cache_unlink_once(cache)
    assert cache.exists()


def test_registry_records_the_path(tmp_path: Path) -> None:
    """The guard keys on the string path, which is what the lock protects."""
    cache = tmp_path / "responses.sqlite"
    sources_base.refresh_cache_unlink_once(cache)
    assert str(cache) in sources_base._refreshed_cache_paths


def test_concurrent_callers_unlink_at_most_once(tmp_path: Path) -> None:
    """`-j N` workers racing on one cache path still get a single unlink."""
    from concurrent.futures import ThreadPoolExecutor

    cache = tmp_path / "responses.sqlite"
    cache.write_text("stale")
    unlinked: list[int] = []

    real_unlink = type(cache).unlink

    def counting_unlink(self, *args, **kwargs):
        unlinked.append(1)
        return real_unlink(self, *args, **kwargs)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(type(cache), "unlink", counting_unlink)
        with ThreadPoolExecutor(max_workers=8) as ex:
            for future in [
                ex.submit(sources_base.refresh_cache_unlink_once, cache)
                for _ in range(16)
            ]:
                future.result()
    assert len(unlinked) == 1


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
