"""
Pytest bootstrap.

Importing ``comicbox.box`` first primes the module cache and avoids a
latent circular import: ``comicbox.config`` transitively pulls in the
full ``comicbox.box`` chain via ``comicbox.formats``, which then circles
back to ``comicbox.config.get_config``. Loading ``comicbox.box``
up-front sets the import order so the cycle resolves cleanly. Test
modules can then import ``comicbox.config.*`` directly.
"""

import comicbox.box  # noqa: F401  # pyright: ignore[reportUnusedImport]
