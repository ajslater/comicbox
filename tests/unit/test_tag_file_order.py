"""Tag files are written in one fixed order, whatever the hash seed (B12)."""

from __future__ import annotations

import os
import subprocess
import sys
from typing import TYPE_CHECKING

from tests.const import CIX_CBZ_SOURCE_PATH

if TYPE_CHECKING:
    from pathlib import Path

_WRITE = """
import shutil, sys, zipfile
from pathlib import Path
from comicbox.write import write_metadata
path = Path(sys.argv[1])
shutil.copy(sys.argv[2], path)
write_metadata(path, {"summary": "x"}, formats=["COMIC_INFO", "METRON_INFO", "COMICBOX_JSON", "COMET"])
with zipfile.ZipFile(path) as archive:
    print([n for n in archive.namelist() if n.endswith((".xml", ".json"))])
"""


def test_tag_files_are_written_in_one_order(tmp_path: Path) -> None:
    orders = set()
    for seed in ("0", "1", "2", "3"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        done = subprocess.run(  # noqa: S603 - this interpreter, a fixed script
            [
                sys.executable,
                "-c",
                _WRITE,
                str(tmp_path / f"{seed}.cbz"),
                str(CIX_CBZ_SOURCE_PATH),
            ],
            capture_output=True,
            text=True,
            env=env,
            check=True,
        )
        orders.add(done.stdout.strip().splitlines()[-1])
    assert len(orders) == 1, orders
