"""
Comic archive.

Reads and writes metadata via the included metadata package.
Reads data using libarchive via archi.
"""

import zipfile

from logging import getLogger
from pathlib import Path

import rarfile

from comicbox.config import get_config
from comicbox.exceptions import UnsupportedArchiveTypeError
from comicbox.logging import init_logging
from comicbox.metadata import comicapi
from comicbox.metadata.comet import CoMet
from comicbox.metadata.comic_base import IMAGE_EXT_RE
from comicbox.metadata.comic_base import ComicBaseMetadata
from comicbox.metadata.comic_xml import ComicXml
from comicbox.metadata.comicbookinfo import ComicBookInfo
from comicbox.metadata.comicinfoxml import ComicInfoXml
from comicbox.metadata.filename import FilenameMetadata


RECOMPRESS_SUFFIX = ".comicbox_tmp_zip"
CBZ_SUFFIX = ".cbz"
init_logging()
LOG = getLogger(__name__)


class ComicArchive(object):
    """
    Represent a comic archive.

    Contains the compressed archive file and its parsed metadata
    """

    PARSER_CLASSES = (ComicInfoXml, ComicBookInfo, CoMet)
    FILENAMES = set((CoMet.FILENAME, ComicInfoXml.FILENAME))

    def __init__(self, path, metadata=None, config=None):
        """Initialize the archive with a path to the archive."""
        if config is None:
            config = get_config()
        self.config = config
        self.set_path(path)
        self.metadata = ComicBaseMetadata(metadata=metadata)
        self.raw = {}
        self.cover_image_data = None
        self._parse_metadata()

    def set_path(self, path):
        """Set the path and determine the archive type."""
        self._path = Path(path)
        if zipfile.is_zipfile(self._path):
            self.archive_cls = zipfile.ZipFile
        elif rarfile.is_rarfile(self._path):
            self.archive_cls = rarfile.RarFile
        else:
            raise UnsupportedArchiveTypeError(f"Unsupported archive type: {self._path}")

    def _get_archive(self, mode="r"):
        return self.archive_cls(self._path, mode=mode)  # type: ignore

    def get_path(self):
        """Get the path for the archive."""
        return self._path

    def namelist(self):
        """Get the archive file namelist."""
        with self._get_archive() as archive:
            return sorted(archive.namelist())

    def _parse_xml_metadata(self, fn, xml_parser_cls, flag, archive):
        """Run the correct parser for the xml file."""
        md_filename = str(xml_parser_cls.FILENAME)
        if Path(fn).name.lower() != md_filename.lower() or not flag:
            return {}

        data = archive.read(fn)
        if self.config.raw:
            self.raw[md_filename] = data
        parser = xml_parser_cls(string=data)
        return parser.metadata

    def _parse_metadata_entries(self, archive):
        """Get the filenames and file based metadata."""
        cix_md = {}
        comet_md = {}
        for fn in sorted(archive.namelist()):
            cix_md.update(
                self._parse_xml_metadata(
                    fn, ComicInfoXml, self.config.comicinfoxml, archive
                )
            )
            comet_md.update(
                self._parse_xml_metadata(fn, CoMet, self.config.comet, archive)
            )
        return cix_md, comet_md

    def _get_archive_comment(self, archive):
        """Get the comment field from an archive."""
        if not archive:
            archive = self._get_archive()
        comment = archive.comment
        if isinstance(comment, bytes):
            comment = comment.decode()
        return comment

    def _parse_metadata_comments(self, archive):
        if not self.config.comicbookinfo:
            return {}
        comment = self._get_archive_comment(archive)
        parser = ComicBookInfo(string=comment)
        cbi_md = parser.metadata
        if self.config.raw:
            self.raw["ComicBookInfo Archive Comment"] = comment
        return cbi_md

    def _parse_metadata_filename(self):
        if not self.config.filename:
            return {}
        parser = FilenameMetadata(path=self._path)
        if self.config.raw:
            self.raw["Filename"] = self._path.name
        return parser.metadata

    def _parse_metadata(self):
        if (
            self.metadata.metadata
            and not self.config.metadata
            and not self.config.cover
        ):
            return
        md_list = []
        if self.config.filename:
            filename_md = self._parse_metadata_filename()
            md_list += [filename_md]
            self.metadata.synthesize_metadata(md_list)

        if not (
            self.config.comicinfoxml
            or self.config.comicbookinfo
            or self.config.comet
            or self.config.cover
        ):
            return
        with self._get_archive() as archive:
            if (
                self.config.comicinfoxml
                or self.config.comicbookinfo
                or self.config.comet
            ):
                cbi_md = self._parse_metadata_comments(archive)
                cix_md, comet_md = self._parse_metadata_entries(archive)
                # order of the md list is very important, lowest to highest
                # precedence.
                md_list += [comet_md, cbi_md, cix_md]
                self.metadata.synthesize_metadata(md_list)
                self._ensure_page_metadata(archive)
            if self.config.cover:
                self.cover_image_data = self._get_cover_image(archive)

    def get_num_pages(self):
        """Return the number of pages."""
        return self.metadata.get_num_pages()

    def _ensure_page_metadata(self, archive):
        """Ensure page metadata exists."""
        compute = False
        for key in ("page_count", "cover_image"):
            if not self.metadata.metadata.get(key):
                compute = True
        if compute:
            namelist = sorted(archive.namelist())
            self.metadata.compute_page_metadata(namelist)

    def get_pages(self, page_from):
        """Generate all pages starting with page number."""
        with self._get_archive() as archive:
            self._ensure_page_metadata(archive)
            pagenames = self.metadata.get_pagenames_from(page_from)
            for pagename in pagenames:
                with archive.open(pagename) as page:
                    yield page.read()

    def get_page_by_filename(self, filename):
        """Return data for a single page by filename."""
        with self._get_archive() as archive:
            with archive.open(filename) as page:
                return page.read()

    def get_page_by_index(self, index):
        """Get the page data by index."""
        with self._get_archive() as archive:
            self._ensure_page_metadata(archive)
            filename = self.metadata.get_pagename(index)
            with archive.open(filename) as page:
                return page.read()

    def extract_pages(self, page_from, root_path="."):
        """Extract pages from archive and write to a path."""
        root_path = Path(root_path)
        if not root_path.is_dir():
            raise ValueError(
                f"Must extract pages to a directory. {str(root_path)} "
                "is not a directory"
            )
        with self._get_archive() as archive:
            self._ensure_page_metadata(archive)
            filenames = self.metadata.get_pagenames_from(page_from)
            for fn in filenames:
                with archive.open(fn) as page:
                    if self.config.dry_run:
                        LOG.info(f"Not extracting page from {self._path}: {fn}")
                        continue
                    full_path = Path(root_path) / Path(fn).name
                    with full_path.open("wb") as page_file:
                        page_file.write(page.read())

    def extract_cover_as(self, path):
        """Extract the cover image to a destination file."""
        with self._get_archive() as archive:
            self._ensure_page_metadata(archive)
            cover_fn = self.metadata.get_cover_page_filename()
            if not cover_fn:
                return
            if self.config.dry_run:
                LOG.info(f"Not extracting cover from {self._path}: {cover_fn}")
                return
            output_path = Path(path)
            if output_path.is_dir():
                output_path = output_path / Path(cover_fn).name
            with archive.open(cover_fn) as page:
                with output_path.open("wb") as cover_file:
                    cover_file.write(page.read())

    def _get_cover_image(self, archive):
        """Return cover image data."""
        self._ensure_page_metadata(archive)
        cover_fn = self.metadata.get_cover_page_filename()
        if not cover_fn:
            return
        try:
            data = archive.read(cover_fn)
        except Exception as exc:
            LOG.error(f"{self._path} reading cover: {cover_fn}")
            raise exc
        return data

    def get_cover_image(self):
        """Get the cover image."""
        if not self.cover_image_data:
            with self._get_archive() as archive:
                self.cover_image_data = self._get_cover_image(archive)
        return self.cover_image_data

    def get_metadata(self):
        """Return the metadata from the archive."""
        return self.metadata.metadata

    def recompress(self, filename=None, data=None):
        """Recompress the archive optionally replacing a file."""
        if self.config.dry_run:
            LOG.info(f"Not recompressing: {self._path}")
            return

        new_path = self._path.with_suffix(CBZ_SUFFIX)
        if new_path.is_file() and new_path != self._path:
            raise ValueError(f"{new_path} already exists.")

        tmp_path = self._path.with_suffix(RECOMPRESS_SUFFIX)
        with self._get_archive() as archive:
            if self.config.delete_tags:
                comment = b""
            else:
                comment = archive.comment
            if isinstance(comment, str):
                comment = comment.encode()
            with zipfile.ZipFile(
                tmp_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
            ) as zf:
                skipnames = set()
                if filename:
                    skipnames.add(filename)
                if self.config.delete_tags:
                    skipnames.add(self.FILENAMES)
                for info in sorted(archive.infolist(), key=lambda i: i.filename):
                    if info.filename.lower() in skipnames:
                        continue
                    if IMAGE_EXT_RE.search(info.filename) is None:
                        compress = zipfile.ZIP_DEFLATED
                    else:
                        # images usually end up slightly larger with
                        # zip compression
                        compress = zipfile.ZIP_STORED
                    zf.writestr(
                        info.filename,
                        archive.read(info),
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
        if self.config.delete_rar:
            LOG.info(f"converted to: {new_path}")
            if new_path.is_file():
                old_path.unlink()
                LOG.info(f"removed: {old_path}")

    def write_metadata(self, md_class, recompute_page_sizes=True):
        """Write metadata using the supplied parser class."""
        if self.config.dry_run:
            LOG.info(f"Not writing metadata for: {self._path}")
            return
        parser = md_class(metadata=self.get_metadata())
        if recompute_page_sizes and isinstance(parser, ComicInfoXml):
            self.compute_pages_tags()
        if isinstance(parser, (ComicXml, CoMet)):
            self.recompress(parser.FILENAME, parser.to_string())
        elif isinstance(parser, ComicBookInfo):
            with self._get_archive("a") as archive:
                comment = parser.to_string().encode()
                archive.comment = comment
        else:
            raise ValueError(f"Unsupported metadata writer {md_class}")

    def to_comicapi(self):
        """Export to comicapi style metadata."""
        return comicapi.export(self.get_metadata())

    def import_file(self, filename):
        """Try to import metada from a file and then write it into the comic."""
        from xml.etree.ElementTree import ParseError

        from simplejson.errors import JSONDecodeError

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
            self.metadata.metadata = md.metadata
            self.write_metadata(success_class)

    def export_files(self):
        """Export metadata to all supported file formats."""
        if self.config.dry_run:
            LOG.info("Not exporting files.")
            return
        for parser_cls in self.PARSER_CLASSES:
            md = parser_cls(self.get_metadata())
            path = Path(str(parser_cls.FILENAME))
            md.to_file(path)

    def compute_pages_tags(self):
        """Recompute the tag image sizes for ComicRack."""
        with self._get_archive() as archive:
            infolist = archive.infolist()
        parser = ComicInfoXml(metadata=self.get_metadata())
        parser.compute_pages_tags(infolist)
        self.metadata.metadata["pages"] = parser.metadata.get("pages")

    def compute_page_count(self):
        """Compute the page count from images in the archive."""
        self.metadata.compute_page_count()

    def rename_file(self):
        """Rename the archive."""
        if self.config.dry_run:
            LOG.info(f"Not reaming file: {self._path}")
            return

        car = FilenameMetadata(self.metadata)
        self._path = car.to_file(self._path)

    def print_raw(self):
        """Print raw metadtata."""
        for key, val in self.raw.items():
            print("-" * 10, key, "-" * 10)
            if isinstance(val, bytes):
                val = val.decode()
            print(val)
