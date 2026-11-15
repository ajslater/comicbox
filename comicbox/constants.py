"""
Cross-package data-model constants.

These live in a top-level module (not under `comicbox.formats.*`) so
that low-level consumers like `comicbox.formats.base.transforms.spec`
and `comicbox.readinglists` can import them without re-entering the
formats package during its own initialization.
"""

# Comicbox-native root.
ROOT_TAG = "comicbox"
ROOT_KEYPATH = ROOT_TAG
