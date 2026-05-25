"""
Hermetic isolation for unit tests.

Without this, any unit test that exercises the config / credentials
chain (``get_config``, ``Comicbox(config=args)``) inherits the
developer's ``~/.config/comicbox/config.yaml`` and ``COMICBOX_*`` env
vars. Test outcomes then depend on host state — e.g. a test that
asserts an unconfigured source is skipped passes locally only when the
developer has no Metron creds.

The fixture:

* strips every ``COMICBOX_*`` env var (covers confuse's ``set_env``
  prefix and the direct reads in ``credentials.read_credential_env`` /
  ``env.read_online_env``);
* points ``COMICBOXDIR`` at an empty tmpdir so confuse's
  ``_add_user_source`` finds no ``config.yaml``.

The package's ``config_default.yaml`` is still loaded, so tests get the
real defaults — just nothing from the user's machine.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _hermetic_comicbox_env(  # pyright: ignore[reportUnusedFunction]
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Strip ``COMICBOX_*`` env vars and isolate confuse from user config."""
    for key in list(os.environ):
        if key.startswith("COMICBOX"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("COMICBOXDIR", str(tmp_path))
