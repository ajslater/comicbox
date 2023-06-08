"""Utility functions for testing metadata."""
import os
import shutil
import zipfile
from pathlib import Path
from pprint import pprint

from deepdiff.diff import DeepDiff
from fitz import fitz

from comicbox.comic_archive import ComicArchive
from comicbox.config import get_config

TEST_FILES_PATH = Path("tests/test_files")
TMP_ROOT = Path("/tmp")  # noqa: S108
SOURCE_ARCHIVE_PATH = TEST_FILES_PATH / "Captain Science #001.cbz"


def read_metadata(archive_path, metadata):
    """Read metadata and compare to dict fixture."""
    with ComicArchive(archive_path) as car:
        disk_md = car.get_metadata()
    pprint(disk_md)
    pprint(metadata)
    diff = DeepDiff(disk_md, metadata, ignore_order=True)
    pprint(diff)
    assert not diff


def _create_test_cbz(tmp_path, new_test_cbz_path, metadata, config):
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
    config = get_config(config)
    with ComicArchive(new_test_cbz_path, config=config, metadata=metadata) as car:
        # write the metadata to the empty archive
        car.write()


def write_metadata(tmp_path, new_test_cbz_path, metadata, config):
    """Create a test metadata file, read it back and compare the original."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    _create_test_cbz(tmp_path, new_test_cbz_path, metadata, config)
    read_metadata(new_test_cbz_path, metadata)
    shutil.rmtree(tmp_path)


def _create_test_pdf(metadata, new_test_pdf_path, config):
    """Create a new empty PDF file."""
    doc = fitz.Document()
    doc.new_page()  # type: ignore
    doc.save(new_test_pdf_path, garbage=4, clean=1, deflate=1, pretty=0)
    doc.close()
    config = get_config(config)
    with ComicArchive(new_test_pdf_path, config=config, metadata=metadata) as car:
        car.write()


def write_metadata_pdf(tmp_path, new_test_pdf_path, metadata, config):
    """Copy the test metadata pdf and write to it."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    _create_test_pdf(metadata, new_test_pdf_path, config)
    read_metadata(new_test_pdf_path, metadata)
    shutil.rmtree(tmp_path)
