"""Utility functions for testing metadata."""
import shutil
import zipfile

from pathlib import Path

from comicbox.comic_archive import ComicArchive
from comicbox.metadata.comic_base import ComicBaseMetadata


TEST_FILES_PATH = Path("tests/test_files")
TMP_ROOT = Path("/tmp")


def read_metadata(archive_path, metadata):
    """Read metadata and compare to dict fixture."""
    disk_car = ComicArchive(archive_path)
    md = ComicBaseMetadata(metadata)
    assert disk_car.metadata == md


def create_test_file(tmp_path, new_test_cbz_path, metadata, md_type):
    """Create a test file and write metadata to it."""
    # Create an empty file to write to
    tmp_path.mkdir(exist_ok=True)
    with zipfile.ZipFile(new_test_cbz_path, mode="w") as zf:
        assert len(zf.namelist()) == 0

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
    md = ComicBaseMetadata(metadata)
    assert disk_car.metadata == md
