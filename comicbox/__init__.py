"""Comicbox."""

from contextlib import suppress
from os import environ

if environ.get("COMICBOX_DEBUG"):
    # Dev convenience only. Gated on a comicbox-specific variable (NOT
    # PYTHONDEVMODE, a standard Python mode downstream consumers enable)
    # and tolerant of icecream being absent — it's a dev-group dependency
    # that production installs don't ship.
    with suppress(ImportError):
        from icecream import install  # pyright: ignore[reportPrivateImportUsage]

        install()
