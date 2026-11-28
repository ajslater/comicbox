"""
Every comicbox module imports cleanly when it is the first one imported.

An import cycle hides as long as something else happens to import the
right module first: the test suite's conftest, or a consumer's own
import order. So each module is imported here into an interpreter that
holds no comicbox module yet. The modules are split between a few
interpreters run side by side, and each purges comicbox from
``sys.modules`` before the next import, so a cycle can never be masked
by an earlier module.
"""

from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING

import comicbox

if TYPE_CHECKING:
    from collections.abc import Sequence

_PACKAGE_DIR = Path(comicbox.__file__).parent
_INTERPRETERS = 8
_DEAD_PROXY = "http://127.0.0.1:9"

# Runs in each child: import every named module first, in turn.
_CHILD = """
import importlib, sys, traceback
failed = []
for name in sys.argv[1:]:
    for loaded in [m for m in sys.modules if m.partition(".")[0] == "comicbox"]:
        del sys.modules[loaded]
    try:
        importlib.import_module(name)
    except Exception:
        failed.append(name + ": " + traceback.format_exc().splitlines()[-1])
    if "pdffile" in sys.modules:
        failed.append(name + ": imported pdffile, which must stay lazy")
        del sys.modules["pdffile"]
print("\\n".join(failed))
sys.exit(1 if failed else 0)
"""


def _module_names() -> list[str]:
    names = []
    for path in sorted(_PACKAGE_DIR.rglob("*.py")):
        parts = path.relative_to(_PACKAGE_DIR.parent).with_suffix("").parts
        if parts[-1] == "__init__":
            parts = parts[:-1]
        names.append(".".join(parts))
    return names


def _import_each(names: Sequence[str], env: dict[str, str]) -> str:
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", _CHILD, *names],
        capture_output=True,
        check=False,
        cwd=_PACKAGE_DIR.parent,
        env=env,
        text=True,
        timeout=300,
    )
    if result.returncode == 0:
        return ""
    return result.stdout.strip() or result.stderr.strip()


def test_every_module_imports_first(tmp_path: Path) -> None:
    names = _module_names()
    assert "comicbox.config.online.build" in names
    env = {
        **os.environ,
        "COMICBOXDIR": str(tmp_path),
        "COMICBOX_ONLINE__CACHE__DIR": str(tmp_path / "online-cache"),
        "HTTPS_PROXY": _DEAD_PROXY,
        "HTTP_PROXY": _DEAD_PROXY,
        "ALL_PROXY": _DEAD_PROXY,
    }
    chunks = [names[start::_INTERPRETERS] for start in range(_INTERPRETERS)]
    with ThreadPoolExecutor(max_workers=_INTERPRETERS) as pool:
        failures = list(pool.map(lambda chunk: _import_each(chunk, env), chunks))
    assert not any(failures), "\n".join(out for out in failures if out)
