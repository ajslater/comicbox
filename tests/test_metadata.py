"""Utility functions for testing metadata."""
import os
import shutil
import zipfile

from pathlib import Path

from comicbox.comic_archive import ComicArchive
from comicbox.metadata.comic_base import ComicBaseMetadata


TEST_FILES_PATH = Path("tests/test_files")
TMP_ROOT = Path("/tmp")
SOURCE_ARCHIVE_PATH = TEST_FILES_PATH / "Captain Science #001.cbz"


def read_metadata(archive_path, metadata):
    """Read metadata and compare to dict fixture."""
    disk_car = ComicArchive(archive_path)
    md = ComicBaseMetadata(metadata=metadata)
    assert disk_car.metadata == md


def create_test_file(tmp_path, new_test_cbz_path, metadata, md_type):
    """Create a test file and write metadata to it."""
    # Create an minimal file to write to
    extract_path = tmp_path / "extract"
    extract_path.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(SOURCE_ARCHIVE_PATH) as zf:
        zf.extractall(extract_path)
    with zipfile.ZipFile(new_test_cbz_path, mode="w") as zf:
        for root, _, filenames in os.walk(extract_path):
            root_path = Path(root)
            for fn in sorted(filenames):
                if fn.endswith(".xml"):
                    continue
                full_fn = root_path / fn
                relative_path = full_fn.relative_to(extract_path)
                zf.write(full_fn, arcname=relative_path)
    shutil.rmtree(extract_path)

    # Create an archive object with the fixture data
    car = ComicArchive(new_test_cbz_path, metadata)
    # write the metadata to the empty archive
    car.write_metadata(md_type)


def write_metadata(tmp_path, new_test_cbz_path, metadata, md_type):
    """Create a test metadata file, read it back and compare the original."""
    create_test_file(tmp_path, new_test_cbz_path, metadata, md_type)
    # read data back from the test file and then cleanup
    disk_car = ComicArchive(new_test_cbz_path)
    shutil.rmtree(tmp_path)

    # comparison metadata direct from example data
    md = ComicBaseMetadata(metadata=metadata)
    assert disk_car.metadata == md
