"""Utility functions for testing metadata."""

import shutil
from collections.abc import Mapping
from copy import deepcopy
from difflib import ndiff
from pathlib import Path
from pprint import pprint
from types import MappingProxyType

import fitz
from deepdiff.diff import DeepDiff

from comicbox.box import Comicbox
from comicbox.schemas.comicbookinfo import LAST_MODIFIED_TAG
from comicbox.schemas.comicbox_mixin import (
    NOTES_KEY,
    PAGE_COUNT_KEY,
    PAGES_KEY,
    ROOT_TAG,
    UPDATED_AT_KEY,
)
from comicbox.transforms.base import BaseTransform
from tests.const import (
    EMPTY_CBZ_SOURCE_PATH,
    TEST_DATETIME,
    TEST_FILES_DIR,
    TEST_METADATA_DIR,
    TEST_WRITE_NOTES,
    TMP_ROOT_DIR,
)


def get_tmp_dir(filename: str):
    """Get a tmp dir for a test file."""
    dirname = Path(filename).with_suffix("").name
    return TMP_ROOT_DIR / dirname


def my_cleanup(tmp_dir: Path):
    """Cleanup tmp dir."""
    shutil.rmtree(tmp_dir, ignore_errors=True)
    assert not tmp_dir.exists()


def my_setup(tmp_dir: Path, source_path: Path | None = None):
    """Set up tmp dir."""
    my_cleanup(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    assert tmp_dir.exists()
    if source_path:
        shutil.copy(source_path, tmp_dir)
        new_path = tmp_dir / source_path.name
        assert new_path.exists()


def diff_strings(a, b):
    """Debug string diffs."""
    diff = ndiff(a.splitlines(keepends=True), b.splitlines(keepends=True))
    print("".join(diff), end="")
    for i, s in enumerate(diff):
        if s[0] == " ":
            continue
        if s[0] == "-":
            print(f'Delete "{s[-1]}" from position {i}')
        elif s[0] == "+":
            print(f'Add "{s[-1]}" to position {i}')


def read_metadata(  # noqa: PLR0913
    archive_path,
    metadata,
    read_config,
    ignore_updated_at: bool,
    ignore_notes: bool,
    page_count=None,
):
    """Read metadata and compare to dict fixture."""
    read_config.comicbox.print = "nslc"
    print(archive_path)
    with Comicbox(archive_path, config=read_config) as car:
        car.print_out()
        disk_md = MappingProxyType(car.get_metadata())
    if page_count is not None:
        disk_md = dict(disk_md)
        disk_md[ROOT_TAG][PAGE_COUNT_KEY] = page_count
        if pages := disk_md.get(PAGES_KEY):
            if page_count:
                disk_md[PAGES_KEY] = pages[:page_count]
            else:
                disk_md.pop(PAGES_KEY, None)
        disk_md = MappingProxyType(disk_md)
    print(f"{ignore_updated_at=} {ignore_notes=}")
    if ignore_updated_at:
        metadata = dict(metadata)
        metadata[ROOT_TAG].pop(UPDATED_AT_KEY, None)
        disk_md = dict(disk_md)
        disk_md[ROOT_TAG].pop(UPDATED_AT_KEY, None)
    if ignore_notes:
        metadata = dict(metadata)
        metadata[ROOT_TAG].pop(NOTES_KEY, None)
        disk_md[ROOT_TAG].pop(NOTES_KEY, None)
    pprint(metadata)
    pprint(disk_md)
    diff = DeepDiff(metadata, disk_md, ignore_order=True)
    pprint(diff)
    assert not diff


_NOTES_TAGS = ("notes:", r'"notes":', "<Notes>", "<pdf:Producer>")


def _prune_lines(lines, ignore_last_modified, ignore_notes, ignore_updated_at):
    pruned_lines = []
    for line in lines:
        if ignore_last_modified and f'"{LAST_MODIFIED_TAG}":' in line:
            continue
        if ignore_notes:
            skip = False
            for tag in _NOTES_TAGS:
                if tag in line:
                    skip = True
            if skip:
                continue
        if ignore_updated_at and UPDATED_AT_KEY in line:
            continue
        pruned_lines.append(line)
    return pruned_lines


def _prune_same_lines(
    a_lines,
    b_lines,
    ignore_last_modified: bool,
    ignore_notes: bool,
    ignore_updated_at: bool,
):
    a_lines = _prune_lines(
        a_lines, ignore_last_modified, ignore_notes, ignore_updated_at
    )
    b_lines = _prune_lines(
        b_lines, ignore_last_modified, ignore_notes, ignore_updated_at
    )
    return a_lines, b_lines


def _prune_strings(
    a_str,
    b_str,
    ignore_last_modified: bool,
    ignore_notes: bool,
    ignore_updated_at: bool,
):
    a_lines = a_str.splitlines()
    b_lines = b_str.splitlines()
    a_lines, b_lines = _prune_same_lines(
        a_lines, b_lines, ignore_last_modified, ignore_notes, ignore_updated_at
    )
    a_str = "\n".join(a_lines)
    b_str = "\n".join(b_lines)
    return a_str, b_str


def compare_files(
    path_a,
    path_b,
    ignore_last_modified: bool,
    ignore_notes: bool,
    ignore_updated_at: bool,
):
    """Compare file contents."""
    with path_a.open("r") as file_a, path_b.open("r") as file_b:
        a_lines = file_a.readlines()
        b_lines = file_b.readlines()

    a_lines, b_lines = _prune_same_lines(
        a_lines, b_lines, ignore_last_modified, ignore_notes, ignore_updated_at
    )

    for line_a, line_b in zip(a_lines, b_lines, strict=False):
        if line_a != line_b:
            print(f"{path_a}: {line_a}")
            print(f"{path_b}: {line_b}")
            print("".join(b_lines))
            return False
    return True


class TestParser:
    """Generic parser tester."""

    __test__ = False

    def __init__(  # noqa: PLR0913
        self,
        transform_class: type[BaseTransform],
        test_fn: Path | str,
        read_reference_metadata: Mapping,
        read_native_dict: Mapping,
        read_reference_string: str,
        read_config,
        write_config,
        write_reference_metadata: Mapping | None = None,
        write_native_dict: Mapping | None = None,
        write_reference_string: str | None = None,
        export_fn=None,
    ):
        """Initialize common variables."""
        self.transform_class = transform_class
        self.schema = transform_class.SCHEMA_CLASS(path=test_fn)
        self.tmp_dir = TMP_ROOT_DIR / f"test_{transform_class.__name__}"
        self.test_fn = Path(test_fn)
        self.read_reference_metadata = read_reference_metadata
        self.read_reference_native_dict = read_native_dict
        self.read_reference_string = read_reference_string
        if write_reference_metadata:
            self.write_reference_metadata = write_reference_metadata
        else:
            self.write_reference_metadata = self.read_reference_metadata

        self.saved_wrm = deepcopy(dict(self.write_reference_metadata))

        if write_native_dict:
            self.write_reference_native_dict = write_native_dict
        else:
            self.write_reference_native_dict = self.read_reference_native_dict
        if write_reference_string:
            self.write_reference_string = write_reference_string
        else:
            self.write_reference_string = self.read_reference_string
        self.reference_path = TEST_FILES_DIR / self.test_fn
        if export_fn is None:
            self.reference_export_path = (
                TEST_METADATA_DIR / self.schema.FILENAME.lower()
            )
        else:
            self.reference_export_path = TEST_METADATA_DIR / export_fn
        self.read_config = read_config
        self.write_config = write_config
        self.export_path = self.tmp_dir / self.schema.FILENAME

    def setup_method(self):
        """Create the tmp dir."""
        my_setup(self.tmp_dir)

    def teardown_method(self):
        """Remove the tmp dir."""
        my_cleanup(self.tmp_dir)

    def _test_from(self, md):
        pprint(self.read_reference_metadata)
        pprint(md)
        diff = DeepDiff(self.read_reference_metadata, md)
        pprint(diff)
        assert not diff

    def test_from_metadata(self):
        """Test assign metadata."""
        pruned = self.read_reference_metadata
        with Comicbox(metadata=pruned) as car:
            md = car.get_metadata()
        self._test_from(md)

    def test_from_dict(self):
        """Test load from native dict."""
        with Comicbox() as car:
            car.add_source(self.read_reference_native_dict, self.transform_class)
            md = car.get_metadata()
        self._test_from(md)

    def test_from_string(self):
        """Test load from string."""
        with Comicbox() as car:
            car.add_source(self.read_reference_string, self.transform_class)
            md = car.get_metadata()
        print(self.read_reference_string)
        self._test_from(md)

    def test_from_file(self):
        """Test load from an export file."""
        print(f"{self.reference_export_path=}")
        with Comicbox() as car:
            car.add_file_source(self.reference_export_path, self.transform_class)
            md = car.get_metadata()
        self._test_from(md)

    def compare_dict(self, test_dict):
        """Compare native dicts."""
        from_dict = deepcopy(dict(self.write_reference_native_dict))
        to_dict = dict(test_dict)
        from_dict.pop(UPDATED_AT_KEY, None)
        to_dict.pop(UPDATED_AT_KEY, None)
        pprint(self.write_reference_native_dict)
        pprint(test_dict)
        diff = DeepDiff(from_dict, to_dict)
        pprint(diff)
        assert not diff

    def to_dict(self, **kwargs):
        """Export metadata to native dict."""
        with Comicbox(metadata=self.write_reference_metadata) as car:
            return car.to_dict(transform_class=self.transform_class, **kwargs)

    def test_to_dict(self, **kwargs):
        """Test export metadata to native dict."""
        test_dict = self.to_dict(**kwargs)
        self.compare_dict(test_dict)

    def to_string(self, **kwargs):
        """Export metadata to string."""
        with Comicbox(metadata=self.write_reference_metadata) as car:
            return car.to_string(transform_class=self.transform_class, **kwargs)

    def compare_string(self, test_str):
        """Compare strings."""
        print(self.write_reference_string)
        print(test_str)
        from_str, to_str = _prune_strings(
            self.write_reference_string,
            test_str,
            ignore_last_modified=True,
            ignore_notes=False,
            ignore_updated_at=True,
        )
        diff_strings(from_str, to_str)
        assert from_str == to_str

    def test_to_string(self, **kwargs):
        """Test export to string."""
        test_str = self.to_string(**kwargs)
        self.compare_string(test_str)

    def test_to_file(self, export_fn=None, **kwargs):
        """Test export to a metadata file."""
        self.setup_method()
        with Comicbox(metadata=self.write_reference_metadata) as car:
            car.to_file(
                self.export_path.parent,
                transform_class=self.transform_class,
                **kwargs,
            )
        assert self.export_path.exists()
        if export_fn:
            reference_export_path = TEST_METADATA_DIR / export_fn
        else:
            reference_export_path = self.reference_export_path
        assert compare_files(
            reference_export_path,
            self.export_path,
            ignore_last_modified=False,
            ignore_notes=False,
            ignore_updated_at=True,
        )
        self.teardown_method()

    def test_md_read(self, archive_path=None, page_count=None):
        """Read metadtata from an archive."""
        if archive_path is None:
            archive_path = self.reference_path
        read_metadata(
            archive_path,
            self.read_reference_metadata,
            self.read_config,
            ignore_updated_at=False,
            ignore_notes=False,
            page_count=page_count,
        )

    def test_pdf_read(self):
        """Ignore stamps for pdf."""
        read_metadata(
            self.reference_path,
            self.read_reference_metadata,
            self.read_config,
            ignore_updated_at=True,
            ignore_notes=True,
        )

    def _create_test_cbz(self, new_test_cbz_path):
        """Create a test file and write metadata to it."""
        shutil.copy(EMPTY_CBZ_SOURCE_PATH, new_test_cbz_path)
        config = deepcopy(self.write_config)
        config.comicbox.updated_at = TEST_DATETIME.isoformat()
        config.comicbox.print = "slcd"
        with Comicbox(
            new_test_cbz_path, config=config, metadata=self.write_reference_metadata
        ) as car:
            car.write()
            car.print_out()

    def write_metadata(self, new_test_cbz_path, page_count=0):
        """Create a test metadata file, read it back and compare the original."""
        tmp_path = new_test_cbz_path.parent
        tmp_path.mkdir(parents=True, exist_ok=True)
        self._create_test_cbz(new_test_cbz_path)
        read_metadata(
            new_test_cbz_path,
            self.write_reference_metadata,
            self.read_config,
            ignore_updated_at=True,
            ignore_notes=True,
            page_count=page_count,
        )
        shutil.rmtree(tmp_path)

    def test_md_write(self, page_count=0):
        """Write metadtata to an archive."""
        new_fn = self.test_fn.with_suffix(".cbz")
        new_cbz_path = self.tmp_dir / new_fn
        self.write_metadata(
            new_cbz_path,
            page_count=page_count,
        )

    def _create_test_pdf(self, new_test_pdf_path):
        """Create a new empty PDF file."""
        try:
            doc = fitz.Document()
            doc.new_page()  # type: ignore[reportAttributeAccessIssue]
            doc.save(new_test_pdf_path, garbage=4, clean=1, deflate=1, pretty=0)
            doc.close()
            pprint(self.write_reference_metadata)
            config = deepcopy(self.write_config)
            config.comicbox.updated_at = TEST_DATETIME.isoformat()
            with Comicbox(
                new_test_pdf_path,
                config=config,
                metadata=self.write_reference_metadata,
            ) as car:
                car.write()
        except NameError as exc:
            reason = "fitz not imported from comicbox-pdffile"
            raise AssertionError(reason) from exc

    def write_metadata_pdf(
        self,
        new_test_pdf_path,
    ):
        """Copy the test metadata pdf and write to it."""
        tmp_path = new_test_pdf_path.parent
        tmp_path.mkdir(parents=True, exist_ok=True)
        self._create_test_pdf(new_test_pdf_path)
        read_metadata(
            new_test_pdf_path,
            self.write_reference_metadata,
            self.read_config,
            ignore_updated_at=True,
            ignore_notes=True,
        )
        shutil.rmtree(tmp_path)

    def test_pdf_write(self):
        """Special pdf write test."""
        test_pdf_path = self.tmp_dir / self.test_fn
        self.write_metadata_pdf(test_pdf_path)


def create_write_metadata(read_metadata, notes=TEST_WRITE_NOTES):
    """Create a write metadata from read metadata."""
    result = deepcopy(dict(read_metadata))
    result[ROOT_TAG]["notes"] = notes
    return MappingProxyType(result)


def create_write_dict(read_dict, schema_class, notes_tag, notes=TEST_WRITE_NOTES):
    """Create a write dict from read dict."""
    write_dict = deepcopy(dict(read_dict))
    write_dict[schema_class.ROOT_TAGS[0]][notes_tag] = notes
    return MappingProxyType(write_dict)
