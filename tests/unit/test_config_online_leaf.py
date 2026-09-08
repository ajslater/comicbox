"""
``comicbox.config.online.settings`` must stay an import leaf.

``comicbox.formats.*`` imports these settings at module scope, so a
runtime import back into ``comicbox.formats`` would close a cycle. The
import graph already leans on this edge being one-way: it's why
``config/computed.py`` and ``box/init.py`` defer their imports and why
``tests/conftest.py`` primes ``comicbox.box`` first.

Asserted against the source rather than a live import, because importing
any ``comicbox.config`` submodule also runs the package ``__init__``,
which legitimately imports ``comicbox.formats.sources`` — that would
mask what these modules do themselves.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import comicbox.config

_CONFIG_DIR = Path(comicbox.config.__file__).parent

# Modules the formats package imports, which therefore may not import it
# back at runtime.
_LEAF_MODULES = (
    "settings.py",
    "online/settings.py",
    "online/template.py",
)


def _runtime_imports(path: Path) -> set[str]:
    """Collect module names imported at module scope, unconditionally."""
    tree = ast.parse(path.read_text())
    imported: set[str] = set()
    # Only bare module-scope statements bind at import time. Iterating the
    # body rather than walking the tree skips both ``if TYPE_CHECKING``
    # blocks and the deferred-import-inside-a-function escape hatch.
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    return imported


@pytest.mark.parametrize("relpath", _LEAF_MODULES)
def test_module_does_not_import_formats(relpath: str) -> None:
    """A settings module never reaches back into the formats package."""
    path = _CONFIG_DIR / relpath
    offenders = sorted(
        name for name in _runtime_imports(path) if name.startswith("comicbox.formats")
    )
    assert not offenders, f"{relpath} imports {offenders} at runtime"


def test_the_probe_detects_a_formats_import(tmp_path: Path) -> None:
    """The check above fails when the import it forbids is present."""
    module = tmp_path / "sample.py"
    module.write_text(
        "from typing import TYPE_CHECKING\n"
        "from comicbox.formats.sources import MetadataSources\n"
        "if TYPE_CHECKING:\n"
        "    from comicbox.formats import MetadataFormats\n"
    )
    assert "comicbox.formats.sources" in _runtime_imports(module)


def test_type_checking_imports_are_allowed(tmp_path: Path) -> None:
    """A TYPE_CHECKING-only import doesn't count against the leaf property."""
    module = tmp_path / "sample.py"
    module.write_text(
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from comicbox.formats import MetadataFormats\n"
    )
    offenders = {
        name for name in _runtime_imports(module) if name.startswith("comicbox.formats")
    }
    assert not offenders
