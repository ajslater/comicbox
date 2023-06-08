"""Comic Archive.

Reads and writes metadata via the included metadata package.
Reads data using libarchive via archi.
"""
import shutil
import stat
from functools import wraps
from json import JSONDecodeError
from logging import getLogger
from pathlib import Path
from pprint import pprint
from tarfile import TarFile, TarInfo, is_tarfile
from tarfile import open as tarfile_open
from typing import Callable, Optional, Union

from confuse import AttrDict
from defusedxml.ElementTree import ParseError
from rarfile import RarFile, is_rarfile
from zipfile_deflate64 import (
    ZIP_DEFLATED,
    ZIP_STORED,
    ZipFile,
    is_zipfile,
)

from comicbox.config import get_config
from comicbox.exceptions import UnsupportedArchiveTypeError
from comicbox.logging import init_logging
from comicbox.metadata import comicapi
from comicbox.metadata.comet import CoMet
from comicbox.metadata.comic_base import IMAGE_EXT_RE, ComicBaseMetadata
from comicbox.metadata.comic_xml import ComicXml
from comicbox.metadata.comicbookinfo import ComicBookInfo
from comicbox.metadata.comicinfoxml import ComicInfoXml
from comicbox.metadata.filename import FilenameMetadata
from comicbox.metadata.pdf import PDFParser
from comicbox.pdf_file import PDFFile

RECOMPRESS_SUFFIX = ".comicbox_tmp_zip"
CBZ_SUFFIX = ".cbz"
init_logging()
LOG = getLogger(__name__)


def _archive_close(f):
    @wraps(f)
    def wrapper(self, *args, **kwargs):
        result = f(self, *args, **kwargs)
        if self._config.close_fd:
            self.close()
        return result

    return wrapper


class ComicArchive:
    """Represent a comic archive.

    Contains the compressed archive file and its parsed metadata
    """

    PARSER_CLASSES = (ComicInfoXml, ComicBookInfo, CoMet)
    FILENAMES = frozenset((CoMet.FILENAME, ComicInfoXml.FILENAME))
    _PAGE_KEYS = frozenset(("page_count", "cover_image"))
    _PAGES_KEYS = frozenset(frozenset(("pages",)) | _PAGE_KEYS)
    _RAW_CBI_KEY = "ComicBookInfo Archive Comment"
    _RAW_FILENAME_KEY = "Filename"
    _RAW_PDF_KEY = "PDF"
    _MODE_EXECUTABLE = stat.S_IXUSR ^ stat.S_IXGRP ^ stat.S_IXOTH
    _COMMENT_ARCHIVE_TYPES = (ZipFile, RarFile)

    def __init__(
        self,
        path: Union[Path, str],
        config: Optional[AttrDict] = None,
        metadata: Optional[dict] = None,
    ):
        """Initialize the archive with a path to the archive.

        path: the path to the comic archive
        config: a confuse AttrDict. If None, ComicArchive generates its own from the
            environment.
        metadata: a comicbox metadata dict to use instead of gathering the metadata
            from the path.
        """
        self._path: Path = Path(path)
        if config is None:
            config = get_config()
        self._config: AttrDict = config
        self._set_archive_cls()
        self._archive: Union[ZipFile, RarFile, TarFile, PDFFile, None] = None
        self._metadata: ComicBaseMetadata = ComicBaseMetadata(
            path=self._path, metadata=metadata
        )
        self._raw: dict = {}

    def __enter__(self):
        """Context enter."""
        return self

    def __exit__(self, *_exc):
        """Context close."""
        self.close()

    @classmethod
    def check_unrar_executable(cls) -> bool:
        """Check for the unrar executable."""
        unrar_path = shutil.which("unrar")
        if not unrar_path:
            reason = "'unrar' not on path"
            raise UnsupportedArchiveTypeError(reason)
        mode = Path(unrar_path).stat().st_mode
        if not bool(mode & cls._MODE_EXECUTABLE):
            reason = f"'{unrar_path}' not executable"
            raise UnsupportedArchiveTypeError(reason)
        return True

    def _set_archive_cls(self):
        """Set the path and determine the archive type."""
        self._archive_cls: Callable
        self._file_type: str
        if is_zipfile(self._path):
            self._archive_cls = ZipFile
            self._file_type = "CBZ"
        elif is_rarfile(self._path):
            if self._config.check_unrar:
                self.check_unrar_executable()
            self._archive_cls = RarFile
            self._file_type = "CBR"
        elif is_tarfile(self._path):
            self._archive_cls = tarfile_open
            self._file_type = "CBT"
        elif PDFFile.is_pdffile(self._path):
            PDFFile.check_import()
            self._archive_cls = PDFFile
            self._file_type = "PDF"
        else:
            reason = f"Unsupported archive type: {self._path}"
            raise UnsupportedArchiveTypeError(reason)

    def get_file_type(self):
        """Return archive type string."""
        return self._file_type

    def _get_archive(self):
        """Set archive instance open for reading."""
        if not self._archive:
            self._archive = self._archive_cls(self._path)
        return self._archive

    def _archive_namelist(self):
        """Get list of files in the archive."""
        archive = self._get_archive()
        if isinstance(archive, TarFile):
            namelist = archive.getnames()
        else:
            namelist = archive.namelist()
        return sorted(namelist)

    def _archive_infolist(self):
        """Get info list of members from the archive."""
        archive = self._get_archive()
        if isinstance(archive, TarFile):
            infolist = archive.getmembers()
        else:
            infolist = archive.infolist()
        fn_attr = "name" if self._archive_cls == tarfile_open else "filename"
        infolist = sorted(infolist, key=lambda i: getattr(i, fn_attr))
        return infolist, fn_attr

    def _archive_readfile(self, filename, to_pixmap=False) -> bytes:
        """Read an archive file to memory."""
        archive = self._get_archive()
        data = b""
        if isinstance(archive, TarFile):
            file_obj = archive.extractfile(filename)
            if file_obj:
                data = file_obj.read()
        elif to_pixmap and isinstance(archive, PDFFile):
            data = archive.read(filename, True)
        else:
            data = archive.read(filename)
        return data

    def _get_raw_files_metadata(self):
        """Get raw metadata from files in the archive."""
        # create parser_classes_dict
        all_parser_classes = {
            CoMet: self._config.read_comet,
            ComicInfoXml: self._config.read_comicinfoxml,
        }
        parser_classes = {}
        for parser_class, flag in all_parser_classes.items():
            if flag and not self._raw.get(parser_class.FILENAME):
                parser_classes[parser_class.FILENAME] = parser_class

        # search filenames for metadata files and read.
        result_parsers = {}
        for fn in self._archive_namelist():
            lower_name = Path(fn).name.lower()
            parser_class = parser_classes.get(lower_name)
            if parser_class and not self._raw.get(parser_class.FILENAME):
                data = self._archive_readfile(fn)
                self._raw[parser_class.FILENAME] = data
                result_parsers[parser_class] = data
                del parser_classes[parser_class.FILENAME]
                if not parser_classes:
                    break
        return result_parsers

    def _parse_files_metadata(self):
        """Run the correct parser for the each archive file's metadata."""
        result_parsers = self._get_raw_files_metadata()
        files_md = {}
        for parser_class, data in result_parsers.items():
            parser = parser_class(path=self._path, string=data)
            files_md[parser_class] = parser.metadata
        return files_md

    def _get_raw_archive_comment(self):
        """Get the comment field from an archive."""
        if (
            self._archive_cls != tarfile_open
            and self._config.read_comicbookinfo
            and not self._raw.get(self._RAW_CBI_KEY)
        ):
            archive = self._get_archive()
            if isinstance(archive, self._COMMENT_ARCHIVE_TYPES):
                comment = archive.comment
            else:
                comment = None

            if isinstance(comment, bytes):
                comment = comment.decode(errors="replace")
            if comment:
                self._raw[self._RAW_CBI_KEY] = comment
        return self._raw.get(self._RAW_CBI_KEY)

    def _parse_metadata_comments(self):
        """Parse the metadata comments with CBI."""
        data = self._get_raw_archive_comment()
        if not data:
            return {}
        parser = ComicBookInfo(path=self._path, string=data)
        return parser.metadata

    def _get_raw_pdf_metadata(self):
        if self._RAW_PDF_KEY not in self._raw:
            if self._archive_cls != PDFFile:
                return None
            archive = self._get_archive()
            if not isinstance(archive, PDFFile):
                return None
            raw = archive.get_metadata()
            self._raw[self._RAW_PDF_KEY] = raw
        return self._raw[self._RAW_PDF_KEY]

    def _parse_pdf_metadata(self):
        pdf_md = self._get_raw_pdf_metadata()
        parser = PDFParser(path=self._path, native_dict=pdf_md)
        return parser.metadata

    def _get_raw_filename(self):
        """Get the filename form the path."""
        if not self._config.read_filename:
            return None
        if not self._raw.get(self._RAW_FILENAME_KEY):
            data = self._path.name
            self._raw[self._RAW_FILENAME_KEY] = data
        return self._raw.get(self._RAW_FILENAME_KEY)

    def _parse_metadata_filename(self):
        """Parse metadata from the filename."""
        if not self._config.read_filename:
            return None
        data = self._get_raw_filename()
        if data is None:
            return {}
        parser = FilenameMetadata(path=data, metadata_path=data)
        return parser.metadata

    def _ensure_page_metadata(self):
        """Ensure page metadata exists."""
        if (
            not self._PAGE_KEYS.issubset(self._metadata.metadata)
            or self._metadata.get_num_pages() is None
        ):
            namelist = self._archive_namelist()
            is_pdf = self._archive_cls == PDFFile
            self._metadata.set_page_metadata(namelist, is_pdf)

    def _normalize_metadata(self):
        """Map familiar keys to native format keys."""
        md = self._config.metadata
        if not md:
            return md
        normal_md = {}
        for key, value in md.items():
            new_key = key
            for parser in self.PARSER_CLASSES:
                if native_key := parser.KEY_MAP.get(key):
                    new_key = native_key
                    break
            normal_md[new_key] = value
        return normal_md

    def add_metadata(self, metadata):
        """Add metadata to the existing metadata."""
        md_list = [metadata]
        self._metadata.synthesize_metadata(md_list)

    def _parse_metadata(self):
        """Parse all enabled metadata."""
        md_list = []
        filename_md = self._parse_metadata_filename()
        if filename_md:
            md_list += [filename_md]
        pdf_md = self._parse_pdf_metadata()
        if pdf_md:
            md_list += [pdf_md]
        if self._archive_cls != PDFFile:
            files_md = self._parse_files_metadata()
            comet_md = files_md.get(CoMet)
            if comet_md:
                md_list += [comet_md]
            cbi_md = self._parse_metadata_comments()
            if cbi_md:
                md_list += [cbi_md]
            cix_md = files_md.get(ComicInfoXml)
            if cix_md:
                md_list += [cix_md]
        if self._config.metadata:
            normal_md = self._normalize_metadata()
            md_list += [normal_md]
        # order of the md list is very important, lowest to highest
        # precedence.
        self._metadata.synthesize_metadata(md_list)
        self._ensure_page_metadata()

    def _set_raw_metadata(self):
        """Set only the raw metadata."""
        self._get_raw_filename()
        self._get_raw_archive_comment()
        self._get_raw_files_metadata()
        self._get_raw_pdf_metadata()

    def _write_cbi_comment(self, parser):
        """Write a cbi comment to an archive."""
        if self._archive_cls not in self._COMMENT_ARCHIVE_TYPES:
            reason = "Cannot write ComicBookInfo comments to this file."
            raise TypeError(reason)
        self.close()
        with self._archive_cls(self._path, "a") as append_archive:
            if not isinstance(append_archive, self._COMMENT_ARCHIVE_TYPES):
                reason = "Cannot write ComicBookInfo comments to this file."
                raise TypeError(reason)
            comment = parser.to_string().encode(errors="replace")
            append_archive.comment = comment

    def close(self):
        """Close the open archive."""
        try:
            if self._archive and hasattr(self._archive, "close"):
                self._archive.close()
        except Exception as exc:
            LOG.warning(f"closing archive: {exc}")
        finally:
            self._archive = None

    @_archive_close
    def get_num_pages(self):
        """Return the number of pages."""
        self._ensure_page_metadata()
        return self._metadata.get_num_pages()

    @_archive_close
    def get_pages(self, page_from=0, page_to=-1, to_pixmap=False):
        """Generate all pages starting with page number."""
        self._ensure_page_metadata()
        pagenames = self._metadata.get_pagenames_from(page_from, page_to)
        if pagenames:
            for pagename in pagenames:
                yield self._archive_readfile(pagename, to_pixmap)

    @_archive_close
    def get_page_by_filename(self, filename, to_pixmap=False):
        """Return data for a single page by filename."""
        return self._archive_readfile(filename, to_pixmap)

    @_archive_close
    def get_page_by_index(self, index, to_pixmap=False):
        """Get the page data by index."""
        self._ensure_page_metadata()
        filename = self._metadata.get_pagename(index)
        return self._archive_readfile(filename, to_pixmap)

    def _extract_page(self, path, fn, to_pixmap=False):
        if self._archive_cls == PDFFile:
            path = path.with_suffix(PDFFile.SUFFIX)
        with path.open("wb") as page_file:
            page_file.write(self._archive_readfile(fn, to_pixmap))

    @_archive_close
    def extract_pages(self, page_from=None, page_to=None, root_path="."):
        """Extract pages from archive and write to a path."""
        root_path = Path(root_path)
        if not root_path.is_dir():
            reason = (
                f"Must extract pages to a directory. {root_path!s} "
                "is not a directory"
            )
            raise ValueError(reason)
        self._ensure_page_metadata()
        pagenames = self._metadata.get_pagenames_from(page_from, page_to)
        if pagenames:
            for fn in pagenames:
                if self._config.dry_run:
                    LOG.info(f"Not extracting page from {self._path}: {fn}")
                    continue
                full_path = Path(root_path) / Path(fn).name
                self._extract_page(full_path, fn)

    @_archive_close
    def extract_cover_as(self, path):
        """Extract the cover image to a destination file."""
        self._ensure_page_metadata()
        cover_fn = self._metadata.get_cover_page_filename()
        if not cover_fn:
            LOG.warning(f"{self._path} could not find cover filename")
            return
        if self._config.dry_run:
            LOG.info(f"Not extracting cover from {self._path}: {cover_fn}")
            return
        output_path = Path(path)
        if output_path.is_dir():
            output_path = output_path / Path(cover_fn).name
        self._extract_page(output_path, cover_fn)

    @_archive_close
    def get_cover_image(self):
        """Return cover image data."""
        self._ensure_page_metadata()
        cover_fn = self._metadata.get_cover_page_filename()
        if not cover_fn:
            LOG.warning(f"{self._path} could not find cover filename")
            return None
        data = None
        try:
            data = self._archive_readfile(cover_fn, True)
        except Exception as exc:
            LOG.warning(f"{self._path} reading cover: {cover_fn}: {exc}")
        return data

    @_archive_close
    def get_metadata(self):
        """Return the metadata from the archive."""
        if not self._metadata.metadata or bool(
            set(self._metadata.metadata.keys()) - self._PAGES_KEYS
        ):
            self._parse_metadata()
        return self._metadata.metadata

    def _get_comment(self):
        """Get the comment from the archive."""
        comment = b""
        if self._archive_cls in self._COMMENT_ARCHIVE_TYPES:
            if not self._config.delete_tags:
                archive = self._get_archive()
                if isinstance(archive, self._COMMENT_ARCHIVE_TYPES):
                    comment = archive.comment
            if isinstance(comment, str):
                comment = comment.encode(errors="replace")

    def _recompress_write_entry(self, info, fn_attr, skipnames, zf):
        """Write a single entry to the tmpfile."""
        if isinstance(info, TarInfo):
            if not info.size:
                return
        elif not info.file_size:
            # don't try to recompress empty dirs
            return
        fn = getattr(info, fn_attr)
        if fn.lower() in skipnames:
            return

        # images usually end up slightly larger with
        # zip compression, so store them.
        compress = ZIP_DEFLATED if IMAGE_EXT_RE.search(fn) is None else ZIP_STORED
        zf.writestr(
            fn,
            self._archive_readfile(fn, True),
            compress_type=compress,
            compresslevel=9,
        )

    def _recompress_write(self, tmp_path, filename, data, comment):
        """Write files from this archive into the tmpfile."""
        with ZipFile(tmp_path, "w", compression=ZIP_DEFLATED, compresslevel=9) as zf:
            skipnames = set()
            if filename:
                skipnames.add(filename)
            if self._config.delete_tags:
                skipnames.add(self.FILENAMES)
            infolist, fn_attr = self._archive_infolist()
            for info in infolist:
                self._recompress_write_entry(info, fn_attr, skipnames, zf)
            if filename and data:
                zf.writestr(filename, data)
            if comment:
                zf.comment = comment

    @_archive_close
    def recompress(self, filename=None, data=None):
        """Recompress the archive optionally replacing a file."""
        if self._config.dry_run:
            LOG.info(f"Not recompressing: {self._path}")
            return

        new_path = self._path.with_suffix(CBZ_SUFFIX)
        if new_path.is_file() and new_path != self._path:
            reason = f"{new_path} already exists."
            raise ValueError(reason)

        tmp_path = self._path.with_suffix(RECOMPRESS_SUFFIX)

        comment = self._get_comment()
        self._recompress_write(tmp_path, filename, data, comment)

        old_path = self._path
        tmp_path.replace(new_path)
        self._path = new_path
        if old_path.suffix != new_path.suffix:
            LOG.info(f"converted to: {new_path}")
            if self._config.delete_orig and old_path != new_path and new_path.is_file():
                old_path.unlink()
                LOG.info(f"removed: {old_path}")

    def _write_pdf_metadata(self, parser):
        """Write PDF Metadata."""
        if self._config.dry_run:
            LOG.info("Not writing PDF metadata.")
            return
        if self._archive_cls != PDFFile:
            return
        pdf_md = parser.to_dict()
        with PDFFile(self._path) as archive:
            archive.save_metadata(pdf_md)

    def write_metadata(self, md_class, metadata=None, recompute_page_sizes=True):
        """Write metadata using the supplied parser class."""
        if self._config.dry_run:
            LOG.info(f"Not writing metadata for: {self._path}")
            return
        if metadata is None:
            metadata = self.get_metadata()
        parser = md_class(path=self._path, metadata=metadata)
        if recompute_page_sizes and isinstance(parser, ComicInfoXml):
            self.compute_pages_tags()
        if isinstance(parser, (ComicXml, CoMet)):
            self.recompress(parser.FILENAME, parser.to_string())
        elif isinstance(parser, ComicBookInfo):
            self._write_cbi_comment(parser)
        elif isinstance(parser, PDFParser):
            self._write_pdf_metadata(parser)
        else:
            reason = f"Unsupported metadata writer {md_class}"
            raise TypeError(reason)
        LOG.info(f"Wrote: {md_class.__name__}")

    def _get_write_parsers(self):
        """Convert config.write list into parser class list."""
        is_pdf = self._archive_cls == PDFFile
        md_class_dict = {
            ComicInfoXml: self._config.write_comicinfoxml and not is_pdf,
            ComicBookInfo: self._config.write_comicbookinfo and not is_pdf,
            CoMet: self._config.write_comet and not is_pdf,
            PDFParser: self._config.write_pdf and is_pdf,
        }

        md_class_list = []
        for key, value in md_class_dict.items():
            if value:
                md_class_list.append(key)
        return md_class_list

    @_archive_close
    def write(self):
        """Write metadata accourding to config.write list."""
        if self._config.dry_run:
            LOG.info(f"Not writing metadata for: {self._path}")
            return
        md_class_list = self._get_write_parsers()
        metadata = self.get_metadata()
        for md_class in md_class_list:
            # XXX writing bot cix & comet may be ineffecient.
            # If opds.json occurs consider optimizing for writing multiple files.
            self.write_metadata(md_class, metadata)

    def to_comicapi(self):
        """Export to comicapi style metadata."""
        return comicapi.export(self.get_metadata())

    def import_file(self, filename):
        """Try to import metada from a file and then write it into the comic."""
        path = Path(filename)
        success_class = None
        md = None
        for cls in self.PARSER_CLASSES:
            try:
                md = cls(path=path)
                success_class = cls
                break
            except (ParseError, JSONDecodeError):
                pass
        if success_class and md:
            self._metadata.metadata = md.metadata
            self.write_metadata(success_class)

    def export_files(self):
        """Export metadata to all supported file formats."""
        if self._config.dry_run:
            LOG.info("Not exporting files.")
            return
        for parser_cls in self.PARSER_CLASSES:
            md = parser_cls(self.get_metadata())
            path = Path(str(parser_cls.FILENAME))
            md.to_file(path)

    @_archive_close
    def compute_pages_tags(self):
        """Recompute the tag image sizes for ComicRack."""
        infolist, _ = self._archive_infolist()
        metadata = self.get_metadata()
        parser = ComicInfoXml(path=self._path, metadata=metadata)
        parser.compute_pages_tags(infolist)
        self._metadata.metadata["pages"] = parser.metadata.get("pages")

    def rename_file(self):
        """Rename the archive."""
        metadata = self.get_metadata()
        car = FilenameMetadata(metadata=metadata, path=self._path)
        self._path = car.to_file(self._path, dry_run=self._config.dry_run)

    @_archive_close
    def print_raw(self):
        """Print raw metadtata."""
        self._set_raw_metadata()
        for key, val in self._raw.items():
            print("-" * 10, key, "-" * 10)  # noqa: T201
            print_val = val.decode(errors="replace") if isinstance(val, bytes) else val
            pprint(print_val)  # noqa: T203

    def get_path(self):
        """Get the path for the archive."""
        return self._path

    @_archive_close
    def namelist(self):
        """Get the archive file namelist."""
        return self._archive_namelist()

    def print_file_type(self):
        """Print the file type."""
        print(self.get_file_type())  # noqa: T201

    def print_metadata(self):
        """Pretty print the metadata."""
        pprint(self.get_metadata())  # noqa: T203
