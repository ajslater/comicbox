"""
Comic Archive.

Reads and writes metadata via the included metadata package.
Reads data using libarchive via archi.
"""
import tarfile
import zipfile

from functools import wraps
from json import JSONDecodeError
from logging import getLogger
from pathlib import Path
from tarfile import TarInfo
from typing import Callable, Optional, Union

import rarfile

from confuse import AttrDict
from defusedxml.ElementTree import ParseError

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


RECOMPRESS_SUFFIX = ".comicbox_tmp_zip"
CBZ_SUFFIX = ".cbz"
init_logging()
LOG = getLogger(__name__)


def _archive_close(f):
    @wraps(f)
    def wrapper(self, *args, **kwargs):
        result = f(self, *args, **kwargs)
        if self._closefd:
            self.close()
        return result

    return wrapper


class ComicArchive:
    """
    Represent a comic archive.

    Contains the compressed archive file and its parsed metadata
    """

    PARSER_CLASSES = (ComicInfoXml, ComicBookInfo, CoMet)
    FILENAMES = frozenset((CoMet.FILENAME, ComicInfoXml.FILENAME))
    _PAGE_KEYS = frozenset(("page_count", "cover_image"))
    _PAGES_KEYS = frozenset(frozenset(("pages",)) | _PAGE_KEYS)
    _RAW_CBI_KEY = "ComicBookInfo Archive Comment"
    _RAW_FILENAME_KEY = "Filename"

    def __init__(
        self,
        path: Union[Path, str],
        config: Optional[AttrDict] = None,
        metadata: Optional[dict] = None,
        closefd: bool = True,
    ):
        """Initialize the archive with a path to the archive.

        path: the path to the comic archive
        config: a confuse AttrDict. If None, ComicArchive generates its own from the
            environment.
        metadata: a comicbox metadata dict to use instead of gathering the metadata
            from the path.
        closefd: whether or not to close the comic archive after every public method
            call or leave it open. If set to False, you should call
            ComicArchive.close() when done with the comic archive.
        """
        self._path: Path = Path(path)
        if config is None:
            config = get_config()
        self._config: AttrDict = config
        self._set_archive_cls()
        self._archive: Union[
            zipfile.ZipFile, rarfile.RarFile, tarfile.TarFile, None
        ] = None
        self._metadata: ComicBaseMetadata = ComicBaseMetadata(metadata=metadata)
        self._closefd: bool = closefd
        self._raw: dict = {}

    def __enter__(self):
        """Context enter."""
        return self

    def __exit__(self, *_exc):
        """Context close."""
        self.close()

    def _set_archive_cls(self):
        """Set the path and determine the archive type."""
        self._archive_cls: Callable
        if zipfile.is_zipfile(self._path):
            self._archive_cls = zipfile.ZipFile
        elif rarfile.is_rarfile(self._path):
            self._archive_cls = rarfile.RarFile
        elif tarfile.is_tarfile(self._path):
            self._archive_cls = tarfile.open
        else:
            raise UnsupportedArchiveTypeError(f"Unsupported archive type: {self._path}")

    def _get_archive(self):
        """Set archive instance open for reading."""
        if not self._archive:
            self._archive = self._archive_cls(self._path)
        return self._archive

    def _archive_namelist(self):
        """Get list of files in the archive."""
        archive = self._get_archive()
        if isinstance(archive, tarfile.TarFile):
            namelist = archive.getnames()
        else:
            namelist = archive.namelist()
        return sorted(namelist)

    def _archive_infolist(self):
        """Get info list of members from the archive."""
        archive = self._get_archive()
        if isinstance(archive, tarfile.TarFile):
            infolist = archive.getmembers()
        else:
            infolist = archive.infolist()
        if self._archive_cls == tarfile.open:
            fn_attr = "name"
        else:
            fn_attr = "filename"
        infolist = sorted(infolist, key=lambda i: getattr(i, fn_attr))
        return infolist, fn_attr

    def _archive_readfile(self, filename) -> bytes:
        """Read an archive file to memory."""
        archive = self._get_archive()
        data = b""
        if isinstance(archive, tarfile.TarFile):
            file_obj = archive.extractfile(filename)
            if file_obj:
                data = file_obj.read()
        else:
            data = archive.read(filename)
        return data

    def _get_raw_files_metadata(self):
        """Get raw metadata from files in the archive."""
        # create parser_classes_dict
        all_parser_classes = {
            CoMet: self._config.comet,
            ComicInfoXml: self._config.comicinfoxml,
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
            parser = parser_class(string=data)
            files_md[parser_class] = parser.metadata
        return files_md

    def _get_raw_archive_comment(self):
        """Get the comment field from an archive."""
        if (
            self._archive_cls != tarfile.open
            and self._config.comicbookinfo
            and not self._raw.get(self._RAW_CBI_KEY)
        ):
            comment = self._get_archive().comment  # type: ignore
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
        parser = ComicBookInfo(string=data, path=self._path)
        return parser.metadata

    def _get_raw_filename(self):
        """Get the filename form the path."""
        if self._config.filename and not self._raw.get(self._RAW_FILENAME_KEY):
            data = self._path.name
            self._raw[self._RAW_FILENAME_KEY] = data
        return self._raw.get(self._RAW_FILENAME_KEY)

    def _parse_metadata_filename(self):
        """Parse metadata from the filename."""
        data = self._get_raw_filename()
        if data is None:
            return {}
        parser = FilenameMetadata(path=data)
        return parser.metadata

    def _ensure_page_metadata(self):
        """Ensure page metadata exists."""
        if (
            not self._PAGE_KEYS.issubset(self._metadata.metadata)
            or self._metadata.get_num_pages() is None
        ):
            namelist = self._archive_namelist()
            self._metadata.set_page_metadata(namelist)

    def _parse_metadata(self):
        """Parse all enabled metadata."""
        md_list = []
        filename_md = self._parse_metadata_filename()
        if filename_md:
            md_list += [filename_md]
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
            md_list += [self._config.metadata]
        # order of the md list is very important, lowest to highest
        # precedence.
        self._metadata.synthesize_metadata(md_list)
        self._ensure_page_metadata()

    def _set_raw_metadata(self):
        """Set only the raw metadata."""
        self._get_raw_filename()
        self._get_raw_archive_comment()
        self._get_raw_files_metadata()

    def _write_cbi_comment(self, parser):
        """Write a cbi comment to an archive."""
        if self._archive_cls == tarfile.open:
            raise ValueError("Cannot write ComicBookInfo comments to cbt tarfile.")
        self.close()
        with self._archive_cls(self._path, "a") as append_archive:
            comment = parser.to_string().encode(errors="replace")
            append_archive.comment = comment  # type: ignore

    def close(self):
        """Close the open archive."""
        try:
            if self._archive:
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
    def get_pages(self, page_from):
        """Generate all pages starting with page number."""
        self._ensure_page_metadata()
        pagenames = self._metadata.get_pagenames_from(page_from)
        if pagenames:
            for pagename in pagenames:
                yield self._archive_readfile(pagename)

    @_archive_close
    def get_page_by_filename(self, filename):
        """Return data for a single page by filename."""
        data = self._archive_readfile(filename)
        return data

    @_archive_close
    def get_page_by_index(self, index):
        """Get the page data by index."""
        self._ensure_page_metadata()
        filename = self._metadata.get_pagename(index)
        data = self._archive_readfile(filename)
        return data

    def _extract_page(self, path, fn):
        with path.open("wb") as page_file:
            page_file.write(self._archive_readfile(fn))

    @_archive_close
    def extract_pages(self, page_from, root_path="."):
        """Extract pages from archive and write to a path."""
        root_path = Path(root_path)
        if not root_path.is_dir():
            raise ValueError(
                f"Must extract pages to a directory. {str(root_path)} "
                "is not a directory"
            )
        self._ensure_page_metadata()
        pagenames = self._metadata.get_pagenames_from(page_from)
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
            return
        data = None
        try:
            data = self._archive_readfile(cover_fn)
        except Exception as exc:
            LOG.warning(f"{self._path} reading cover: {cover_fn}: {exc}")
        return data

    @_archive_close
    def get_metadata(self):
        """Return the metadata from the archive."""
        if not self._metadata.metadata or bool(
            frozenset(self._metadata.metadata.keys()) - self._PAGES_KEYS
        ):
            self._parse_metadata()
        return self._metadata.metadata

    @_archive_close
    def recompress(self, filename=None, data=None):
        """Recompress the archive optionally replacing a file."""
        if self._config.dry_run:
            LOG.info(f"Not recompressing: {self._path}")
            return

        new_path = self._path.with_suffix(CBZ_SUFFIX)
        if new_path.is_file() and new_path != self._path:
            raise ValueError(f"{new_path} already exists.")

        tmp_path = self._path.with_suffix(RECOMPRESS_SUFFIX)
        comment = b""
        if self._archive_cls != tarfile.open:
            if not self._config.delete_tags:
                comment = self._get_archive().comment  # type: ignore
            if isinstance(comment, str):
                comment = comment.encode(errors="replace")

        with zipfile.ZipFile(
            tmp_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as zf:
            skipnames = set()
            if filename:
                skipnames.add(filename)
            if self._config.delete_tags:
                skipnames.add(self.FILENAMES)
            infolist, fn_attr = self._archive_infolist()
            for info in infolist:
                if isinstance(info, TarInfo):
                    if not info.size:
                        continue
                elif not info.file_size:
                    # don't try to recompress empty dirs
                    continue
                fn = getattr(info, fn_attr)
                if fn.lower() in skipnames:
                    continue
                if IMAGE_EXT_RE.search(fn) is None:
                    compress = zipfile.ZIP_DEFLATED
                else:
                    # images usually end up slightly larger with
                    # zip compression
                    compress = zipfile.ZIP_STORED
                zf.writestr(
                    fn,
                    self._archive_readfile(fn),
                    compress_type=compress,
                    compresslevel=9,
                )
            if filename and data:
                zf.writestr(filename, data)
            if comment:
                zf.comment = comment

        old_path = self._path
        tmp_path.replace(new_path)
        self._path = new_path
        if old_path.suffix != new_path.suffix:
            LOG.info(f"converted to: {new_path}")
        if self._config.delete_rar and new_path.is_file():
            old_path.unlink()
            LOG.info(f"removed: {old_path}")

    def write_metadata(self, md_class, recompute_page_sizes=True):
        """Write metadata using the supplied parser class."""
        if self._config.dry_run:
            LOG.info(f"Not writing metadata for: {self._path}")
            return
        parser = md_class(metadata=self.get_metadata())
        if recompute_page_sizes and isinstance(parser, ComicInfoXml):
            self.compute_pages_tags()
        if isinstance(parser, (ComicXml, CoMet)):
            self.recompress(parser.FILENAME, parser.to_string())
        elif isinstance(parser, ComicBookInfo):
            self._write_cbi_comment(parser)
        else:
            raise ValueError(f"Unsupported metadata writer {md_class}")

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
        parser = ComicInfoXml(metadata=metadata, path=self._path)
        parser.compute_pages_tags(infolist)
        self._metadata.metadata["pages"] = parser.metadata.get("pages")

    def rename_file(self):
        """Rename the archive."""
        if self._config.dry_run:
            LOG.info(f"Not reaming file: {self._path}")
            return

        car = FilenameMetadata(self._metadata)
        self._path = car.to_file(self._path)

    @_archive_close
    def print_raw(self):
        """Print raw metadtata."""
        self._set_raw_metadata()
        for key, val in self._raw.items():
            print("-" * 10, key, "-" * 10)
            if isinstance(val, bytes):
                val = val.decode(errors="replace")
            print(val)

    def get_path(self):
        """Get the path for the archive."""
        return self._path

    @_archive_close
    def namelist(self):
        """Get the archive file namelist."""
        return self._archive_namelist()
