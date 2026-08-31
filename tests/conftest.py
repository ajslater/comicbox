"""
Pytest bootstrap and hermetic isolation for the whole suite.

Importing ``comicbox.box`` first primes the module cache and avoids a
latent circular import: ``comicbox.config`` transitively pulls in the
full ``comicbox.box`` chain via ``comicbox.formats``, which then circles
back to ``comicbox.config.get_config``. Loading ``comicbox.box``
up-front sets the import order so the cycle resolves cleanly. Test
modules can then import ``comicbox.config.*`` directly.

Without the autouse fixture below, any test that exercises the config /
credentials chain (``get_config``, ``Comicbox(config=args)``) inherits
the developer's ``~/.config/comicbox/config.yaml`` and ``COMICBOX_*``
env vars. Test outcomes then depend on host state — e.g. a test that
asserts an unconfigured source is skipped passes locally only when the
developer has no Metron creds. The fixture lives at the suite root (not
under ``tests/unit/``) so integration, schema, and cli tests are
isolated too.

The fixture:

* strips every ``COMICBOX_*`` env var (the prefix of the EnvSource
  mounted on the config tree, so this covers every config key);
* points ``COMICBOXDIR`` at an empty tmpdir so confuse's
  ``_add_user_source`` finds no ``config.yaml``.

The package's ``config_default.yaml`` is still loaded, so tests get the
real defaults — just nothing from the user's machine.
"""

from __future__ import annotations

import os
import sys
import tempfile
from typing import TYPE_CHECKING

import pytest

import comicbox.box  # noqa: F401  # pyright: ignore[reportUnusedImport]

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


def _scrub_environ_at_collection() -> None:
    """
    Apply the hermetic scrub at conftest import (collection) time.

    The autouse fixture below only protects test BODIES. A couple dozen
    test modules call ``get_config()`` at module level, which runs during
    collection — before any fixture — and used to capture the
    developer's real env and ``~/.config/comicbox/config.yaml``.
    conftest imports before every test module, so scrubbing here makes
    those module-level configs hermetic too.
    """
    for key in list(os.environ):
        if key.startswith("COMICBOX"):
            del os.environ[key]
    os.environ["COMICBOXDIR"] = tempfile.mkdtemp(prefix="comicbox-tests-confuse-")


_scrub_environ_at_collection()


@pytest.fixture(autouse=True)
def _hermetic_comicbox_env(  # pyright: ignore[reportUnusedFunction]
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[None]:
    """
    Strip ``COMICBOX_*`` env vars and isolate confuse from user config.

    Also clears the online sources' process-wide client caches on the way
    out. Both Metron and Comic Vine memoize their upstream client by
    credential set at module scope so a batch reuses one connection pool;
    that cache outlives a test, so without this a fake client built with
    throwaway credentials would be handed to every later test that
    happens to reuse them.
    """
    for key in list(os.environ):
        if key.startswith("COMICBOX"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("COMICBOXDIR", str(tmp_path))
    yield
    _reset_shared_online_sessions()


def _reset_shared_online_sessions() -> None:
    """Clear both sources' shared-client caches, if they were imported."""
    comicvine = sys.modules.get("comicbox.formats.comicvine_api.online_source")
    if comicvine is not None:
        comicvine.reset_shared_sessions()
    metron = sys.modules.get("comicbox.formats.metron_api.online_source")
    if metron is not None:
        with metron._session_cache_lock:
            metron._session_cache.clear()
