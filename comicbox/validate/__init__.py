"""
Leaf schema validators.

Lives outside `comicbox/box/` so importing a validator doesn't drag in the
`Comicbox` mixin chain (which loops back through `comicbox.config` →
`comicbox.formats.sources` → `comicbox.formats`). Format packages reference
these classes from their `REGISTRATION`, so they must be importable while
`comicbox.formats.__init__` is still loading.
"""
