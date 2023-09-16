"""Utility functions for testing metadata."""
import shutil
from collections.abc import Mapping
from copy import deepcopy
from difflib import ndiff
from pathlib import Path
from pprint import pprint
from types import MappingProxyType
from typing import Optional, Union

from deepdiff.diff import DeepDiff

try:
    from fitz_new import fitz

    FITZ_IMPORTED = True
except ImportError:
    FITZ_IMPORTED = False

from comicbox.box import Comicbox
from comicbox.schemas.comicbookinfo import LAST_MODIFIED_KEY
from comicbox.schemas.comicbox_base import (
    PAGE_COUNT_KEY,
    PAGES_KEY,
    UPDATED_AT_KEY,
    ComicboxBaseSchema,
    SchemaConfig,
)
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


def my_setup(tmp_dir: Path, source_path: Optional[Path] = None):
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


def read_metadata(archive_path, metadata, read_config, page_count=None):
    """Read metadata and compare to dict fixture."""
    read_config.comicbox.print = "nslc"
    print(archive_path)
    with Comicbox(archive_path, config=read_config) as car:
        car.print_out()
        disk_md = MappingProxyType(car.get_metadata())
    if page_count is not None:
        metadata = dict(metadata)
        metadata[PAGE_COUNT_KEY] = page_count
        if pages := metadata.get(PAGES_KEY):
            if page_count:
                metadata[PAGES_KEY] = pages[:page_count]
            else:
                metadata.pop(PAGES_KEY, None)
        metadata = MappingProxyType(metadata)
    pprint(metadata)
    pprint(disk_md)
    diff = DeepDiff(metadata, disk_md, ignore_order=True)
    pprint(diff)
    assert not diff


_NOTES_TAGS = ("notes:", r'"notes":', "<Notes>", "<pdf:Producer>")


def _prune_lines(lines, ignore_last_modified, ignore_notes, ignore_updated):
    pruned_lines = []
    for line in lines:
        if ignore_last_modified and f'"{LAST_MODIFIED_KEY}":' in line:
            continue
        if ignore_notes:
            skip = False
            for tag in _NOTES_TAGS:
                if tag in line:
                    skip = True
            if skip:
                continue
        if ignore_updated and UPDATED_AT_KEY in line:
            continue
        pruned_lines.append(line)
    return pruned_lines


def compare_files(
    path_a,
    path_b,
    ignore_last_modified=False,
    ignore_notes=False,
    ignore_updated_at=False,
):
    """Compare file contents."""
    with path_a.open("r") as file_a, path_b.open("r") as file_b:
        a_lines = file_a.readlines()
        b_lines = file_b.readlines()

    a_lines = _prune_lines(
        a_lines, ignore_last_modified, ignore_notes, ignore_updated_at
    )
    b_lines = _prune_lines(
        b_lines, ignore_last_modified, ignore_notes, ignore_updated_at
    )

    for line_a, line_b in zip(a_lines, b_lines):
        if line_a != line_b:
            print(f"{path_a}: {line_a}")
            print(f"{path_b}: {line_b}")
            print("".join(b_lines))
            return False
    return True


DUMP_CONFIG = SchemaConfig(stamp=True, updated_at=TEST_DATETIME)


class TestParser:
    """Generic parser tester."""

    __test__ = False

    def __init__(  # noqa PLR0913
        self,
        schema_class: type[ComicboxBaseSchema],
        test_fn: Union[Path, str],
        read_reference_metadata: Mapping,
        read_native_dict: Mapping,
        read_reference_string: str,
        read_config,
        write_config,
        write_reference_metadata: Optional[Mapping] = None,
        write_native_dict: Optional[Mapping] = None,
        write_reference_string: Optional[str] = None,
        export_fn=None,
    ):
        """Initialize common variables."""
        self.schema_class = schema_class
        self.schema = schema_class(test_fn)
        self.tmp_dir = TMP_ROOT_DIR / f"test_{schema_class.__name__}"
        self.test_fn = Path(test_fn)
        self.read_reference_metadata = read_reference_metadata
        self.read_reference_native_dict = read_native_dict
        self.read_reference_string = read_reference_string
        if write_reference_metadata:
            self.write_reference_metadata = write_reference_metadata
        else:
            self.write_reference_metadata = self.read_reference_metadata
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
            self.reference_export_path = TEST_METADATA_DIR / self.schema.FILENAME
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
        diff = DeepDiff(dict(self.read_reference_metadata), md)
        pprint(diff)
        assert not diff

    def test_from_metadata(self):
        """Test assign metadata."""
        pruned = self.schema.prune(self.read_reference_metadata)
        with Comicbox(metadata=pruned) as car:
            md = car.get_metadata()
        self._test_from(md)

    def test_from_dict(self):
        """Test load from native dict."""
        with Comicbox() as car:
            car.add_source(self.read_reference_native_dict, self.schema_class)
            md = car.get_metadata()
        self._test_from(md)

    def test_from_string(self):
        """Test load from string."""
        with Comicbox() as car:
            car.add_source(self.read_reference_string, self.schema_class)
            md = car.get_metadata()
        print(self.read_reference_string)
        self._test_from(md)

    def test_from_file(self):
        """Test load from an export file."""
        print(f"{self.reference_export_path=}")
        with Comicbox() as car:
            car.add_file_source(self.reference_export_path, self.schema_class)
            md = car.get_metadata()
        self._test_from(md)

    def compare_dict(self, test_dict):
        """Compare native dicts."""
        pprint(self.write_reference_native_dict)
        pprint(test_dict)
        diff = DeepDiff(dict(self.write_reference_native_dict), test_dict)
        pprint(diff)
        assert not diff

    def to_dict(self, **kwargs):
        """Export metadata to native dict."""
        with Comicbox(metadata=self.write_reference_metadata) as car:
            return car.to_dict(schema_class=self.schema_class, **kwargs)

        # return self.schema.dump(self.reference_metadata, **kwargs)

    def test_to_dict(self, **kwargs):
        """Test export metadata to native dict."""
        test_dict = self.to_dict(dump_config=DUMP_CONFIG, **kwargs)
        self.compare_dict(test_dict)

    def to_string(self, **kwargs):
        """Export metadata to string."""
        with Comicbox(metadata=self.write_reference_metadata) as car:
            return car.to_string(
                schema_class=self.schema_class, dump_config=DUMP_CONFIG, **kwargs
            )
        # return self.schema.dumps(self.reference_metadata, **kwargs)

    def compare_string(self, test_str):
        """Compare strings."""
        print(self.write_reference_string)
        print(test_str)
        diff_strings(self.write_reference_string, test_str)
        assert self.write_reference_string == test_str

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
                schema_class=self.schema_class,
                dump_config=DUMP_CONFIG,
                **kwargs,
            )
        assert self.export_path.exists()
        if export_fn:
            reference_export_path = TEST_METADATA_DIR / export_fn
        else:
            reference_export_path = self.reference_export_path
        assert compare_files(reference_export_path, self.export_path)
        self.teardown_method()

    def test_md_read(self, archive_path=None, page_count=None):
        """Read metadtata from an archive."""
        if archive_path is None:
            archive_path = self.reference_path
        read_metadata(
            archive_path,
            self.read_reference_metadata,
            self.read_config,
            page_count=page_count,
        )

    def _create_test_cbz(self, new_test_cbz_path):
        """Create a test file and write metadata to it."""
        shutil.copy(EMPTY_CBZ_SOURCE_PATH, new_test_cbz_path)
        ns = self.write_config
        ns.comicbox.print = "m"
        with Comicbox(
            new_test_cbz_path, config=ns, metadata=self.write_reference_metadata
        ) as car:
            car.write(dump_config=DUMP_CONFIG)
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
        assert FITZ_IMPORTED
        doc = fitz.Document()
        doc.new_page()  # type: ignore
        doc.save(new_test_pdf_path, garbage=4, clean=1, deflate=1, pretty=0)
        doc.close()
        pprint(self.write_reference_metadata)
        with Comicbox(
            new_test_pdf_path,
            config=self.write_config,
            metadata=self.write_reference_metadata,
        ) as car:
            car.write(dump_config=DUMP_CONFIG)

    def write_metadata_pdf(
        self,
        new_test_pdf_path,
    ):
        """Copy the test metadata pdf and write to it."""
        tmp_path = new_test_pdf_path.parent
        tmp_path.mkdir(parents=True, exist_ok=True)
        self._create_test_pdf(new_test_pdf_path)
        read_metadata(
            new_test_pdf_path, self.write_reference_metadata, self.read_config
        )
        shutil.rmtree(tmp_path)

    def test_pdf_write(self):
        """Special pdf write test."""
        test_pdf_path = self.tmp_dir / self.test_fn
        self.write_metadata_pdf(test_pdf_path)


def create_write_metadata(read_metadata):
    """Create a write metadata from read metadata."""
    return MappingProxyType(
        {**deepcopy(dict(read_metadata)), "notes": TEST_WRITE_NOTES}
    )


def create_write_dict(read_dict, schema_class, notes_tag):
    """Create a write dict from read dict."""
    write_dict = deepcopy(dict(read_dict))
    write_dict[schema_class.ROOT_TAG][notes_tag] = TEST_WRITE_NOTES
    return MappingProxyType(write_dict)
