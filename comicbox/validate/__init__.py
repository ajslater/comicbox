"""
Leaf schema validators.

Lives outside `comicbox/box/` so importing a validator doesn't drag in the
`Comicbox` mixin chain (which loops back through `comicbox.config` →
`comicbox.formats.sources` → `comicbox.formats`). Format packages name
these classes with a `spec.ValidatorSpec` in their `REGISTRATION`, so
`spec` must be importable while `comicbox.formats.__init__` is still
loading — and, because the modules below pull in `xmlschema` /
`jsonschema` and compile their schemas, nothing here may be imported
until something actually validates.
"""
