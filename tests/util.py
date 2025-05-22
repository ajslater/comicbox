"""Utility functions for testing metadata."""

import re
import shutil
from argparse import Namespace
from collections.abc import Mapping
from copy import deepcopy
from difflib import ndiff
from pathlib import Path
from pprint import pprint
from types import MappingProxyType

import pymupdf
from deepdiff.diff import DeepDiff
from glom import Assign, Delete, glom
from ruamel.yaml import YAML

from comicbox.box import Comicbox
from comicbox.box.pages.covers import PAGES_KEYPATH
from comicbox.formats import MetadataFormats
from comicbox.schemas.comicbookinfo import LAST_MODIFIED_TAG as CBI_LAST_MODIFIED_TAG
from comicbox.schemas.comicbox import (
    EXT_KEY,
    NOTES_KEY,
    PAGE_COUNT_KEY,
    UPDATED_AT_KEY,
    ComicboxSchemaMixin,
)
from comicbox.schemas.metroninfo import LAST_MODIFIED_TAG as METRON_LAST_MODIFIED_TAG
from comicbox.transforms.comicbookinfo import UPDATED_AT_KEYPATH
from tests.const import (
    EMPTY_CBZ_SOURCE_PATH,
    TEST_DATETIME,
    TEST_FILES_DIR,
    TEST_METADATA_DIR,
    TEST_WRITE_NOTES,
    TMP_ROOT_DIR,
)
from tests.validate.validate import validate_path

PRINT_CONFIG = Namespace(comicbox=Namespace(print="slmncd"))
PAGE_COUNT_KEYPATH = f"{ComicboxSchemaMixin.ROOT_KEYPATH}.{PAGE_COUNT_KEY}"
NOTES_KEYPATH = f"{ComicboxSchemaMixin.ROOT_KEYPATH}.{NOTES_KEY}"
EXT_KEYPATH = f"{ComicboxSchemaMixin.ROOT_KEYPATH}.{EXT_KEY}"


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


def assert_diff_strings(a, b):
    """Debug string diffs."""
    if a != b:
        diff = ndiff(a.splitlines(keepends=True), b.splitlines(keepends=True))
        if diff:
            print("".join(diff), end="")  # noqa: T201
        for i, s in enumerate(diff):
            if s[0] == " ":
                continue
            if s[0] == "-":
                print(f'Delete "{s[-1]}" from position {i}')  # noqa: T201
            elif s[0] == "+":
                print(f'Add "{s[-1]}" to position {i}')  # noqa: T201
        assert not diff
    else:
        assert a == b


def read_metadata(  # noqa: PLR0913
    archive_path,
    metadata,
    read_config,
    *,
    ignore_updated_at: bool,
    ignore_notes: bool,
    page_count=None,
    ignore_page_count: bool = False,
    ignore_pages: bool = False,
):
    """Read metadata and compare to dict fixture."""
    read_config.comicbox.print = "slnmcd"

    with Comicbox(archive_path, config=read_config) as car:
        car.print_out()
        disk_md = dict(car.get_metadata())
    metadata = dict(metadata)
    if ignore_page_count:
        glom(metadata, Delete(PAGE_COUNT_KEYPATH, ignore_missing=True))
        glom(disk_md, Delete(PAGE_COUNT_KEYPATH, ignore_missing=True))
    elif page_count is not None:
        glom(metadata, Assign(PAGE_COUNT_KEYPATH, page_count, missing=dict))
    glom(metadata, Assign(EXT_KEYPATH, archive_path.suffix[1:], missing=dict))
    if ignore_updated_at:
        glom(metadata, Delete(UPDATED_AT_KEYPATH, ignore_missing=True))
        glom(disk_md, Delete(UPDATED_AT_KEYPATH, ignore_missing=True))
    if ignore_notes:
        glom(metadata, Delete(NOTES_KEYPATH, ignore_missing=True))
        glom(disk_md, Delete(NOTES_KEYPATH, ignore_missing=True))
    if ignore_pages:
        glom(metadata, Delete(PAGES_KEYPATH, ignore_missing=True))
        glom(disk_md, Delete(PAGES_KEYPATH, ignore_missing=True))
    metadata = MappingProxyType(metadata)
    disk_md = MappingProxyType(disk_md)
    assert_diff(metadata, disk_md)


_NOTES_TAGS = ("notes:", r'"notes":', "<Notes>", "<pdf:Producer>", "&lt;Notes&gt;")
_LAST_MODIFIED_TAGS = (rf'"{CBI_LAST_MODIFIED_TAG}":', rf"<{METRON_LAST_MODIFIED_TAG}>")
_TMP_IGNORE_SUBSTRINGS = ("<identifier>", "pages:", '"pages":')
_MOD_DATE_TAGS = ('"modDate":', "<pdf:ModDate>")
_PAGE_COUNT_TAGS = ('"page_count:"', "<pages>")
_IDENTIFIERS_TAGS = ('"identifiers:"',)
_TAGGER_TAGS = ('"appID":',)


def _prune_lines(  # noqa: PLR0913
    lines,
    ignore_last_modified,
    ignore_notes,
    ignore_updated_at,
    ignore_mod_date,
    *,
    ignore_page_count: bool,
    ignore_identifiers: bool,
    ignore_tagger: bool,
):
    skip_substrings = [*_TMP_IGNORE_SUBSTRINGS]
    if ignore_updated_at:
        skip_substrings += [UPDATED_AT_KEY]
    if ignore_mod_date:
        skip_substrings += _MOD_DATE_TAGS
    if ignore_last_modified:
        skip_substrings += _LAST_MODIFIED_TAGS
    if ignore_notes:
        skip_substrings += _NOTES_TAGS
    if ignore_page_count:
        skip_substrings += _PAGE_COUNT_TAGS
    if ignore_identifiers:
        skip_substrings += _IDENTIFIERS_TAGS
    if ignore_tagger:
        skip_substrings += _TAGGER_TAGS

    skipped_line_re = re.compile("|".join(skip_substrings))

    pruned_lines = []
    for line in lines:
        if skipped_line_re.search(line):
            continue
        pruned_lines.append(line)
    return pruned_lines


def _prune_same_lines(  # noqa: PLR0913
    a_lines,
    b_lines,
    *,
    ignore_last_modified: bool,
    ignore_notes: bool,
    ignore_updated_at: bool,
    ignore_mod_date: bool,
    ignore_page_count: bool,
    ignore_identifiers: bool,
    ignore_tagger: bool,
):
    a_lines = _prune_lines(
        a_lines,
        ignore_last_modified,
        ignore_notes,
        ignore_updated_at,
        ignore_mod_date,
        ignore_page_count=ignore_page_count,
        ignore_identifiers=ignore_identifiers,
        ignore_tagger=ignore_tagger,
    )
    b_lines = _prune_lines(
        b_lines,
        ignore_last_modified,
        ignore_notes,
        ignore_updated_at,
        ignore_mod_date,
        ignore_page_count=ignore_page_count,
        ignore_identifiers=ignore_identifiers,
        ignore_tagger=ignore_tagger,
    )
    return a_lines, b_lines


def _prune_strings(  # noqa: PLR0913
    a_str,
    b_str,
    *,
    ignore_last_modified: bool,
    ignore_notes: bool,
    ignore_updated_at: bool,
    ignore_mod_date: bool,
):
    a_lines = a_str.splitlines()
    b_lines = b_str.splitlines()
    a_lines, b_lines = _prune_same_lines(
        a_lines,
        b_lines,
        ignore_last_modified=ignore_last_modified,
        ignore_notes=ignore_notes,
        ignore_updated_at=ignore_updated_at,
        ignore_mod_date=ignore_mod_date,
        ignore_page_count=False,
        ignore_identifiers=False,
        ignore_tagger=False,
    )
    a_str = "\n".join(a_lines)
    b_str = "\n".join(b_lines)
    return a_str, b_str


def compare_files(  # noqa: PLR0913
    path_a,
    path_b,
    *,
    ignore_last_modified: bool,
    ignore_notes: bool,
    ignore_updated_at: bool,
    ignore_mod_date: bool,
    ignore_page_count: bool,
    ignore_identifiers: bool,
    ignore_tagger: bool,
):
    """Compare file contents."""
    with path_a.open("r") as file_a, path_b.open("r") as file_b:
        a_lines = file_a.readlines()
        b_lines = file_b.readlines()

    a_lines, b_lines = _prune_same_lines(
        a_lines,
        b_lines,
        ignore_last_modified=ignore_last_modified,
        ignore_notes=ignore_notes,
        ignore_updated_at=ignore_updated_at,
        ignore_mod_date=ignore_mod_date,
        ignore_page_count=ignore_page_count,
        ignore_identifiers=ignore_identifiers,
        ignore_tagger=ignore_tagger,
    )

    for line_a, line_b in zip(a_lines, b_lines, strict=False):
        if line_a != line_b:
            print(f"{path_a}: {line_a}")  # noqa: T201
            print(f"{path_b}: {line_b}")  # noqa: T201
            print("".join(b_lines))  # noqa: T201
            return False
    return True


class TestParser:
    """Generic parser tester."""

    __test__ = False

    def __init__(  # noqa: PLR0913
        self,
        fmt: MetadataFormats,
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
        self.fmt = fmt
        self.schema = self.fmt.value.transform_class.SCHEMA_CLASS(path=test_fn)
        self.tmp_dir = TMP_ROOT_DIR / f"test_{fmt.value.label.replace(' ', '-')}"
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
                TEST_METADATA_DIR / self.fmt.value.filename.lower()
            )
        else:
            self.reference_export_path = TEST_METADATA_DIR / export_fn
        self.read_config = read_config
        self.write_config = write_config
        self.export_path = self.tmp_dir / self.fmt.value.filename

    def setup_method(self):
        """Create the tmp dir."""
        my_setup(self.tmp_dir)

    def teardown_method(self):
        """Remove the tmp dir."""
        my_cleanup(self.tmp_dir)

    def _test_from(self, md, page_count=None):
        if page_count is None:
            read_reference_metadata = self.read_reference_metadata
        else:
            read_reference_metadata = deepcopy(dict(self.read_reference_metadata))
            glom(
                read_reference_metadata,
                Assign("comicbox.page_count", page_count, missing=dict),
            )
            read_reference_metadata = MappingProxyType(read_reference_metadata)
        assert_diff(read_reference_metadata, md)

    def test_from_metadata(self):
        """Test assign metadata."""
        pruned = self.read_reference_metadata
        with Comicbox(
            metadata=pruned, fmt=MetadataFormats.COMICBOX_YAML, config=PRINT_CONFIG
        ) as car:
            # car.print_out() debug
            md = car.get_metadata()
        self._test_from(md)

    def test_from_dict(self):
        """Test load from native dict."""
        with Comicbox(config=PRINT_CONFIG) as car:
            car.add_metadata(self.read_reference_native_dict, self.fmt)
            car.print_out()
            md = car.get_metadata()
        self._test_from(md)

    def test_from_string(self):
        """Test load from string."""
        with Comicbox(config=PRINT_CONFIG) as car:
            car.add_metadata(self.read_reference_string, self.fmt)
            # car.print_out() debug
            md = car.get_metadata()
        self._test_from(md)

    def test_from_file(self, page_count=None):
        """Test load from an export file."""
        with Comicbox(config=PRINT_CONFIG) as car:
            car.add_metadata_file(self.reference_export_path, self.fmt)
            # car.print_out() debug
            md = car.get_metadata()
        self._test_from(md, page_count=page_count)

    def compare_dict(self, test_dict):
        """Compare native dicts."""
        from_dict = deepcopy(dict(self.write_reference_native_dict))
        to_dict = dict(test_dict)
        from_dict.pop(UPDATED_AT_KEY, None)
        to_dict.pop(UPDATED_AT_KEY, None)
        assert_diff(from_dict, to_dict)

    def to_dict(self, **kwargs):
        """Export metadata to native dict."""
        with Comicbox(
            metadata=self.write_reference_metadata,
            fmt=MetadataFormats.COMICBOX_YAML,
        ) as car:
            # car.print_out() debug
            return car.to_dict(fmt=self.fmt, **kwargs)

    def test_to_dict(self, **kwargs):
        """Test export metadata to native dict."""
        test_dict = self.to_dict(**kwargs)
        self.compare_dict(test_dict)

    def to_string(self, **kwargs):
        """Export metadata to string."""
        with Comicbox(
            metadata=self.write_reference_metadata, fmt=MetadataFormats.COMICBOX_YAML
        ) as car:
            # car.print_out() debug
            return car.to_string(fmt=self.fmt, **kwargs)

    def compare_string(self, test_str):
        """Compare strings."""
        from_str, to_str = _prune_strings(
            self.write_reference_string,
            test_str,
            ignore_last_modified=True,
            ignore_notes=False,
            ignore_updated_at=True,
            ignore_mod_date=True,
        )
        assert_diff_strings(from_str, to_str)

    def test_to_string(self, **kwargs):
        """Test export to string."""
        test_str = self.to_string(**kwargs)
        self.compare_string(test_str)

    def test_to_file(self, export_fn=None, **kwargs):
        """Test export to a metadata file."""
        self.setup_method()
        with Comicbox(
            metadata=self.write_reference_metadata, fmt=MetadataFormats.COMICBOX_YAML
        ) as car:
            car.to_file(
                self.export_path.parent,
                fmt=self.fmt,
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
            ignore_mod_date=True,
            ignore_page_count=False,
            ignore_identifiers=False,
            ignore_tagger=False,
        )
        self.teardown_method()

    def test_md_read(self, archive_path=None, page_count=None, *, ignore_pages=False):
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
            ignore_pages=ignore_pages,
        )

    def test_pdf_read(self):
        """Ignore stamps for pdf."""
        read_metadata(
            self.reference_path,
            self.read_reference_metadata,
            self.read_config,
            ignore_updated_at=True,
            ignore_notes=True,
            ignore_page_count=True,
        )

    def _create_test_cbz(self, new_test_cbz_path):
        """Create a test file and write metadata to it."""
        shutil.copy(EMPTY_CBZ_SOURCE_PATH, new_test_cbz_path)
        config = deepcopy(self.write_config)
        config.comicbox.updated_at = TEST_DATETIME.isoformat()
        config.comicbox.print = "slmncd"
        with Comicbox(
            new_test_cbz_path,
            config=config,
            metadata=self.write_reference_metadata,
            fmt=MetadataFormats.COMICBOX_YAML,
        ) as car:
            # car.print_out() debug
            car.dump()

    def write_metadata(
        self,
        new_test_cbz_path,
        page_count=None,
        *,
        ignore_pages=False,
    ):
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
            ignore_pages=ignore_pages,
        )
        shutil.rmtree(tmp_path)

    def test_md_write(
        self,
        page_count=None,
        *,
        ignore_pages=False,
    ):
        """Write metadtata to an archive."""
        new_fn = self.test_fn.with_suffix(".cbz")
        new_cbz_path = self.tmp_dir / new_fn
        self.write_metadata(
            new_cbz_path,
            page_count=page_count,
            ignore_pages=ignore_pages,
        )

    def _create_test_pdf(self, new_test_pdf_path):
        """Create a new empty PDF file."""
        try:
            doc = pymupdf.Document()
            doc.new_page()  # pyright: ignore[reportAttributeAccessIssue]
            doc.save(new_test_pdf_path, garbage=4, clean=1, deflate=1, pretty=0)
            doc.close()
            config = deepcopy(self.write_config)
            config.comicbox.updated_at = TEST_DATETIME.isoformat()
            with Comicbox(
                new_test_pdf_path,
                config=config,
                metadata=self.write_reference_metadata,
                fmt=MetadataFormats.COMICBOX_YAML,
            ) as car:
                car.dump()
        except NameError as exc:
            reason = "pymupdf not imported from comicbox-pdffile"
            raise AssertionError(reason) from exc

    def write_metadata_pdf(self, new_test_pdf_path, page_count=None):
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
            page_count=page_count,
        )
        shutil.rmtree(tmp_path)

    def test_pdf_write(self, page_count=None):
        """Special pdf write test."""
        test_pdf_path = self.tmp_dir / self.test_fn
        self.write_metadata_pdf(test_pdf_path, page_count=page_count)


def create_write_metadata(read_metadata, notes=TEST_WRITE_NOTES):
    """Create a write metadata from read metadata."""
    result = deepcopy(dict(read_metadata))
    result[ComicboxSchemaMixin.ROOT_TAG]["notes"] = notes
    return MappingProxyType(result)


def create_write_dict(read_dict, schema_class, notes_tag, notes=TEST_WRITE_NOTES):
    """Create a write dict from read dict."""
    write_dict = deepcopy(dict(read_dict))
    write_dict[schema_class.ROOT_TAG][notes_tag] = notes
    return MappingProxyType(write_dict)


def load_cli_and_compare_dicts(path_a, path_b):
    """Compare cli strings all on one line."""
    yaml = YAML()
    with path_a.open("r") as file_a, path_b.open("r") as file_b:
        dict_a = yaml.load(file_a)
        dict_b = yaml.load(file_b)
    dict_a[ComicboxSchemaMixin.ROOT_TAG].pop(UPDATED_AT_KEY, None)
    dict_b[ComicboxSchemaMixin.ROOT_TAG].pop(UPDATED_AT_KEY, None)
    dict_a[ComicboxSchemaMixin.ROOT_TAG].pop(NOTES_KEY, None)
    dict_b[ComicboxSchemaMixin.ROOT_TAG].pop(NOTES_KEY, None)

    assert_diff(dict_a, dict_b)


def compare_export(test_dir, fn, fmt="", test_fn=None, *, validate=True):
    """Compare exported files."""
    if validate:
        validate_path(fn, fmt=fmt)
    if test_fn is None:
        test_fn = fn.name.lower()
    test_path = test_dir / test_fn
    if fn.name == "comicbox-cli.yaml":
        load_cli_and_compare_dicts(test_path, fn)
    else:
        assert compare_files(
            test_path,
            fn,
            ignore_last_modified=True,
            ignore_notes=True,
            ignore_updated_at=True,
            ignore_mod_date=True,
            ignore_page_count=True,
            ignore_identifiers=True,
            ignore_tagger=True,
        )


def assert_diff(old_map, new_map):
    """Assert no diff and print if there is."""
    if diff := DeepDiff(old_map, new_map, ignore_order=True):
        pprint(old_map)  # noqa: T203
        pprint(new_map)  # noqa: T203
        pprint(diff)  # noqa: T203
    assert not diff
