"""Package name and version."""

import sys
import threading
from contextlib import suppress
from importlib.metadata import PackageNotFoundError, version

PACKAGE_NAME = "comicbox"


def get_version() -> str:
    """Get the current installed comicbox version."""
    v = "dev"
    if "pytest" not in sys.modules:
        with suppress(PackageNotFoundError):
            v = version(PACKAGE_NAME)
    return v


VERSION = get_version()
# Metadata provenance stamp (tagger field + ComicTagger-style notes). Space
# delimiter matches the ComicTagger convention the notes parser round-trips.
DEFAULT_TAGGER = f"{PACKAGE_NAME} {VERSION}"
# HTTP User-Agent for online API clients (simyan, mokkari). Slash delimiter is
# the RFC 9110 product-token convention, distinct from DEFAULT_TAGGER on purpose.
USER_AGENT = f"{PACKAGE_NAME}/{VERSION}"

# How this process is driving comicbox, appended to USER_AGENT as an RFC
# 9110 product comment.
#
# Metron's operators read these logs. When a token exceeds its burst
# limit they have to work out what was behind it, and a bare
# `comicbox/5.0.1` cannot distinguish the CLI's `-j N` thread pool from
# an embedding application (codex) running several processes against one
# token — a difference that changes the diagnosis completely, since
# per-process pacing splits differently in each case. See
# https://github.com/ajslater/comicbox/issues/207, where exactly that
# question could not be answered from the server side.
_ua_lock = threading.Lock()
_ua_entry_point = "lib"
_ua_jobs: int | None = None
_ua_client: str | None = None


def set_user_agent_context(
    entry_point: str, jobs: int | None = None, client: str | None = None
) -> None:
    """
    Record how this process drives comicbox, for the outgoing User-Agent.

    ``entry_point`` is ``"cli"`` or ``"lib"``; ``jobs`` is the worker
    count a batch runs with; ``client`` names an embedding application.

    Call before the first online request: API clients bake the header in
    at construction and are memoized per credential set, so a later
    change does not reach a session that already exists.
    """
    global _ua_entry_point, _ua_jobs, _ua_client  # noqa: PLW0603
    with _ua_lock:
        _ua_entry_point = entry_point
        _ua_jobs = jobs
        _ua_client = client


def user_agent() -> str:
    """Return the User-Agent for outgoing API requests."""
    with _ua_lock:
        parts = [_ua_entry_point]
        if _ua_client:
            parts.append(_ua_client)
        if _ua_jobs and _ua_jobs > 1:
            parts.append(f"jobs={_ua_jobs}")
    return f"{USER_AGENT} ({'; '.join(parts)})"
