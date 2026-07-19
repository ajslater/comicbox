"""Process-wide deduplication for repeated configuration warnings."""

from __future__ import annotations

import threading

from loguru import logger

_seen: set[str] = set()
_lock = threading.Lock()


def warn_once(key: str, message: str) -> None:
    """
    Log `message` at WARNING the first time `key` is seen this process.

    Online sources are rebuilt per file, so a warning emitted during
    client construction (e.g. "this config override is ignored") would
    repeat for every file in a batch run. Deduplicating on a stable key
    keeps the signal at exactly one line per process regardless of which
    source's build path emits it or how often.
    """
    with _lock:
        if key in _seen:
            return
        _seen.add(key)
    logger.warning(message)
