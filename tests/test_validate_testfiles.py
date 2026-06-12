"""Validate test metadata files."""

import os
from pathlib import Path

from comicbox.box.validate import validate_source
from tests.const import TEST_EXPORT_DIR, TEST_METADATA_DIR

# Explicit expected set: a bare count tripwire broke on any fixture add
# and the failure message never named the offending file.
_EXPECTED_TEST_FILES = frozenset(
    {
        "comet-write.xml",
        "comet.xml",
        "comic-book-info.json",
        "comicbox-cli.yaml",
        "comicbox-write.json",
        "comicbox-write.yaml",
        "comicbox.json",
        "comicbox.yaml",
        "comicinfo-write.xml",
        "comicinfo.xml",
        "metroninfo-write.xml",
        "metroninfo.xml",
        "mupdf.json",
        "pdf-metadata.xml",
    }
)
_SUFFIXES = frozenset({"." + ext for ext in ("txt", "xml", "json", "yaml", "yml")})


def _test_dir(root_dir: Path, substring: str = "") -> set[Path]:
    validated = set()
    for root, _, fns in os.walk(root_dir):
        root_path = Path(root)
        for fn in fns:
            if substring and (substring not in fn):
                continue
            path = root_path / fn
            if path.suffix not in _SUFFIXES:
                continue
            validate_source(path)
            validated.add(path)
    return validated


def test_testfiles() -> None:
    """Validate test metadata files used for comparing writes."""
    validated = _test_dir(TEST_EXPORT_DIR)
    validated |= _test_dir(TEST_METADATA_DIR, substring="write")
    names = frozenset(path.name for path in validated)
    assert names == _EXPECTED_TEST_FILES
