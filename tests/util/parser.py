"""Generic parser/round-trip tester used by the schema test suite."""

import shutil
from argparse import Namespace
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pymupdf
from glom import Assign, glom

from comicbox.box import Comicbox
from comicbox.config import get_config
from comicbox.formats import MetadataFormats
from comicbox.formats.comicbox.schema import UPDATED_AT_KEY
from tests.const import (
    EMPTY_CBZ_SOURCE_PATH,
    TEST_FILES_DIR,
    TEST_METADATA_DIR,
    TMP_ROOT_DIR,
)

from .compare import compare_files, prune_strings
from .diff import assert_diff, assert_diff_strings
from .metadata import read_metadata
from .tmp import my_cleanup, my_setup

ROUND_TRIP_PRINT_CONFIG = get_config(
    Namespace(comicbox=Namespace(print=Namespace(phases="slmncd")))
)


class TestParser:
    """Generic parser tester."""

    __test__ = False

    def __init__(  # noqa: PLR0913, PLR0917
        self,
        fmt: MetadataFormats,
        test_fn: Path | str,
        read_reference_metadata: Mapping,
        read_native_dict: Mapping,
        read_reference_string: str,
        read_config: Any,
        write_config: Any,
        write_reference_metadata: Mapping | None = None,
        write_native_dict: Mapping | None = None,
        write_reference_string: str | None = None,
        export_fn: str | None = None,
    ) -> None:
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

    def setup_method(self) -> None:
        """Create the tmp dir."""
        my_setup(self.tmp_dir)

    def teardown_method(self) -> None:
        """Remove the tmp dir."""
        my_cleanup(self.tmp_dir)

    def _test_from(
        self, md: MappingProxyType[str, Any], page_count: int | None = None
    ) -> None:
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

    def test_from_metadata(self) -> None:
        """Test assign metadata."""
        pruned = self.read_reference_metadata
        with Comicbox(
            metadata=pruned,
            fmt=MetadataFormats.COMICBOX_YAML,
            config=ROUND_TRIP_PRINT_CONFIG,
        ) as car:
            # car.print_out() debug
            md = car.get_internal_metadata()
        self._test_from(md)

    def test_from_dict(self) -> None:
        """Test load from native dict."""
        with Comicbox(config=ROUND_TRIP_PRINT_CONFIG) as car:
            car.add_metadata(self.read_reference_native_dict, self.fmt)
            car.print_out()
            md = car.get_internal_metadata()
        self._test_from(md)

    def test_from_string(self) -> None:
        """Test load from string."""
        with Comicbox(config=ROUND_TRIP_PRINT_CONFIG) as car:
            car.add_metadata(self.read_reference_string, self.fmt)
            # car.print_out() debug
            md = car.get_internal_metadata()
        self._test_from(md)

    def test_from_file(self, page_count: int | None = None) -> None:
        """Test load from an export file."""
        with Comicbox(config=ROUND_TRIP_PRINT_CONFIG) as car:
            car.add_metadata_file(self.reference_export_path, self.fmt)
            # car.print_out() debug
            md = car.get_internal_metadata()
        self._test_from(md, page_count=page_count)

    def compare_dict(self, test_dict: dict[str, Any]) -> None:
        """Compare native dicts."""
        from_dict = deepcopy(dict(self.write_reference_native_dict))
        to_dict = dict(test_dict)
        from_dict.pop(UPDATED_AT_KEY, None)
        to_dict.pop(UPDATED_AT_KEY, None)
        assert_diff(from_dict, to_dict)

    def to_dict(self, **kwargs: Any) -> dict[str, Any]:
        """Export metadata to native dict."""
        with Comicbox(
            metadata=self.write_reference_metadata,
            fmt=MetadataFormats.COMICBOX_YAML,
        ) as car:
            # car.print_out() debug
            return car.to_dict(fmt=self.fmt, **kwargs)

    def test_to_dict(self, **kwargs: Any) -> None:
        """Test export metadata to native dict."""
        test_dict = self.to_dict(**kwargs)
        self.compare_dict(test_dict)

    def to_string(self, **kwargs: Any) -> str:
        """Export metadata to string."""
        with Comicbox(
            metadata=self.write_reference_metadata, fmt=MetadataFormats.COMICBOX_YAML
        ) as car:
            # car.print_out() debug
            return car.to_string(fmt=self.fmt, **kwargs)

    def compare_string(self, test_str: str) -> None:
        """Compare strings."""
        from_str, to_str = prune_strings(
            self.write_reference_string,
            test_str,
            ignore_last_modified=True,
            ignore_notes=False,
            ignore_updated_at=True,
            ignore_mod_date=True,
        )
        assert_diff_strings(from_str, to_str)

    def test_to_string(self, **kwargs: Any) -> None:
        """Test export to string."""
        test_str = self.to_string(**kwargs)
        self.compare_string(test_str)

    def test_to_file(self, export_fn: str | None = None, **kwargs: Any) -> None:
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

    def test_md_read(
        self,
        archive_path: Path | None = None,
        page_count: int | None = None,
        *,
        ignore_pages: bool = False,
    ) -> None:
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

    def test_pdf_read(self) -> None:
        """Ignore stamps for pdf."""
        read_metadata(
            self.reference_path,
            self.read_reference_metadata,
            self.read_config,
            ignore_updated_at=True,
            ignore_notes=True,
            ignore_page_count=True,
        )

    def _create_test_cbz(self, new_test_cbz_path: Path) -> None:
        """Create a test file and write metadata to it."""
        shutil.copy(EMPTY_CBZ_SOURCE_PATH, new_test_cbz_path)
        with Comicbox(
            new_test_cbz_path,
            config=self.write_config,
            metadata=self.write_reference_metadata,
            fmt=MetadataFormats.COMICBOX_YAML,
        ) as car:
            # car.print_out() debug
            car.dump()

    def write_metadata(
        self,
        new_test_cbz_path: Path,
        page_count: int | None = None,
        *,
        ignore_pages: bool = False,
    ) -> None:
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
        page_count: int | None = None,
        *,
        ignore_pages: bool = False,
    ) -> None:
        """Write metadtata to an archive."""
        new_fn = self.test_fn.with_suffix(".cbz")
        new_cbz_path = self.tmp_dir / new_fn
        self.write_metadata(
            new_cbz_path,
            page_count=page_count,
            ignore_pages=ignore_pages,
        )

    def _create_test_pdf(self, new_test_pdf_path: Path) -> None:
        """Create a new empty PDF file."""
        try:
            doc = pymupdf.Document()
            doc.new_page()
            doc.save(new_test_pdf_path, garbage=4, clean=1, deflate=1, pretty=0)
            doc.close()
            with Comicbox(
                new_test_pdf_path,
                config=self.write_config,
                metadata=self.write_reference_metadata,
                fmt=MetadataFormats.COMICBOX_YAML,
            ) as car:
                car.dump()
        except NameError as exc:
            reason = "pymupdf not imported from comicbox-pdffile"
            raise AssertionError(reason) from exc

    def write_metadata_pdf(
        self, new_test_pdf_path: Path, page_count: int | None = None
    ) -> None:
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

    def test_pdf_write(self, page_count: int | None = None) -> None:
        """Special pdf write test."""
        test_pdf_path = self.tmp_dir / self.test_fn
        self.write_metadata_pdf(test_pdf_path, page_count=page_count)
