"""Temp-directory lifecycle helpers for tests."""

import shutil
from pathlib import Path

from tests.const import TMP_ROOT_DIR


def get_tmp_dir(filename: str) -> Path:
    """Get a tmp dir for a test file."""
    dirname = Path(filename).with_suffix("").name
    return TMP_ROOT_DIR / dirname


def my_cleanup(tmp_dir: Path) -> None:
    """Cleanup tmp dir."""
    shutil.rmtree(tmp_dir, ignore_errors=True)
    assert not tmp_dir.exists()


def my_setup(tmp_dir: Path, source_path: Path | None = None) -> None:
    """Set up tmp dir."""
    my_cleanup(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    assert tmp_dir.exists()
    if source_path:
        shutil.copy(source_path, tmp_dir)
        new_path = tmp_dir / source_path.name
        assert new_path.exists()
