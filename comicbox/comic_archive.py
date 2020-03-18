"""
Comic archive.

Reads and writes metadata via the included metadata package.
Reads data using libarchive via archi.
"""

import zipfile

from pathlib import Path

import rarfile

from .metadata import comicapi
from .metadata.comet import CoMet
from .metadata.comic_base import ComicBaseMetadata
from .metadata.comic_xml import ComicXml
from .metadata.comicbookinfo import ComicBookInfo
from .metadata.comicinfoxml import ComicInfoXml
from .metadata.filename import FilenameMetadata


class Settings:
    """Settings to control default behavior. Overridden by cli namespace."""

    comicrack = True
    comiclover = True
    comet = True
    filename = True
    raw = False


class ComicArchive(object):
    """
    Represent a comic archive.

    Contains the compressed archive file and its parsed metadata
    """

    RAR_EXTS = (".cbr", ".rar")
    ZIP_EXTS = (".cbz", ".zip")
    PARSER_CLASSES = (ComicInfoXml, ComicBookInfo, CoMet)

    def __init__(self, path, metadata=None, settings=None):
        """Initialize the archive with a path to the archive."""
        if settings is None:
            settings = Settings()
        self.settings = settings
        self.path = Path(path)
        self.metadata = ComicBaseMetadata(metadata)
        self.raw = {}
        self._parse_metadata()

    def _get_archive(self, mode="r"):
        """Get the correct module for type."""
        if zipfile.is_zipfile(self.path):
            return zipfile.ZipFile(self.path, mode=mode)
        elif rarfile.is_rarfile(self.path):
            return rarfile.RarFile(self.path, mode=mode)
        raise ValueError(f"Unsupported archive type: {self.path}")

    def _parse_metadata_entries(self):
        """Get the filenames and file based metadata."""
        cix_md = {}
        comet_md = {}
        with self._get_archive() as archive:
            archive_filenames = archive.namelist()
            for fn in archive_filenames:
                basename = Path(fn).name.lower()
                xml_parser = None
                if basename == ComicInfoXml.XML_FN and self.settings.comicrack:
                    md = cix_md
                    xml_parser = ComicInfoXml()
                    title = "ComicRack"
                elif basename == CoMet.XML_FN and self.settings.comet:
                    md = comet_md
                    xml_parser = CoMet()
                    title = "CoMet"
                if not xml_parser:
                    continue
                with archive.open(fn) as md_file:
                    data = md_file.read()
                    if self.settings.raw:
                        self.raw[title] = data
                    xml_parser.from_string(data)
                    md.update(xml_parser.metadata)
        self.archive_filenames = sorted(archive_filenames)
        return cix_md, comet_md

    def get_archive_comment(self):
        """
        Get the comment field from an archive.

        libarchive doesn't support comments
        Only support cbr & cbz for now.
        Use delayed imports as ComicRack metadata seems more popular.
        """
        if self.path.suffix in self.RAR_EXTS:

            with rarfile.RarFile(str(self.path), "r") as rar_file:
                comment = rar_file.comment
        elif self.path.suffix in self.ZIP_EXTS:
            with zipfile.ZipFile(self.path, "r") as zip_file:
                comment = zip_file.comment
        else:
            comment = ""
        return comment

    def _parse_metadata_comments(self):
        if not self.settings.comiclover:
            return {}
        comment = self.get_archive_comment()
        parser = ComicBookInfo()
        parser.from_string(comment)
        cbi_md = parser.metadata
        if self.settings.raw:
            self.raw["ComicLover"] = comment
        return cbi_md

    def _parse_metadata_filename(self):
        if not self.settings.filename:
            return {}
        parser = FilenameMetadata()
        parser.parse_filename(self.path)
        if self.settings.raw:
            self.raw["Filename"] = self.path.name
        return parser.metadata

    def _parse_metadata(self):
        cix_md, comet_md = self._parse_metadata_entries()
        cbi_md = self._parse_metadata_comments()
        filename_md = self._parse_metadata_filename()

        # order of the md list is very important, lowest to highest
        # precedence.
        md_list = (filename_md, comet_md, cbi_md, cix_md)
        self.metadata.synthesize_metadata(md_list)
        self.metadata.parse_page_names(self.archive_filenames)

    def get_num_pages(self):
        """Retun the number of pages."""
        return self.metadata.get_num_pages()

    def get_pages(self, page_from):
        """Get all pages starting with page number."""
        # TODO turn into generator
        pagenames = self.metadata.get_pagenames_from(page_from)
        pages = []
        with self._get_archive() as archive:
            for pagename in pagenames:
                with archive.open(pagename) as page:
                    pages += [page.read()]
        return pages

    def get_page_by_filename(self, filename):
        """Return data for a single page by filename."""
        with self._get_archive() as archive:
            with archive.open(filename) as page:
                return page.read()

    def get_page_by_index(self, index):
        """Get the page data by index."""
        filename = self.metadata.get_pagename(index)
        return self.get_page_by_filename(filename)

    def get_cover_images(self):
        """Return the cover pages as image data."""
        names = self.metadata.get_cover_page_filenames()
        covers = []
        for name in names:
            covers.append(self.get_page_by_filename(name))
        return covers

    def extract_pages(self, page_from, root_path="."):
        """Extract pages from archive and write to a path."""
        filenames = self.metadata.get_pagenames_from(page_from)
        with self._get_archive() as archive:
            for fn in filenames:
                with archive.open(fn) as page:
                    fn = root_path / fn
                    with open(fn, "wb") as page_file:
                        page_file.write(page.read())

    def extract_covers(self, root_path="."):
        """Exract the cover image."""
        covers = self.get_cover_images()
        index = 0
        for cover in covers:
            fn = root_path / f"cover{index}.jpg"
            with open(fn, "wb") as page_file:
                page_file.write(cover)
            index += 1

    def get_metadata(self):
        """Return the metadata from the archive."""
        return self.metadata.metadata

    def _write_file_metadata(self, parser):
        with self._get_archive("w") as archive:
            data = parser.to_string()
            archive.writestr(
                parser.XML_FN, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9
            )

    def write_metadata(self, md_class, recompute_page_sizes=False):
        """Write metadata using the supplied parser class."""
        parser = md_class(self.metadata.metadata)
        if recompute_page_sizes and isinstance(parser, ComicInfoXml):
            parser.compute_pages_tags()
        if isinstance(parser, (ComicXml, CoMet)):
            self._write_file_metadata(parser)
        elif isinstance(parser, ComicBookInfo):
            with self._get_archive("w") as archive:
                archive.comment = parser.to_string().encode()
        else:
            raise ValueError(f"Unsupported metadata writer {md_class}")

    def convert_to_cbz(self):
        """Convert the archive to cbz for writing."""
        if zipfile.is_zipfile(self.path):
            raise ValueError("already a zipfile.")

        new_path = self.path.with_suffix(".cbz")
        if new_path.is_file():
            raise ValueError("cbz for this comic already exists.")

        with self._get_archive() as archive:
            comment = archive.comment
            if isinstance(comment, str):
                comment = comment.encode()
            with zipfile.ZipFile(
                new_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
            ) as new_zf:
                for name in sorted(archive.namelist()):
                    data = archive.read(name)
                    new_zf.writestr(name, data)
                if comment:
                    new_zf.comment = comment
        return new_path

    def to_comicapi(self):
        """Export to comicapi style metadata."""
        return comicapi.export(self.get_metadata())

    def import_file(self, filename):
        """Try to import metada from a file and then write it into the comic."""
        from simplejson.errors import JSONDecodeError
        from xml.etree.ElementTree import ParseError

        path = Path(filename)
        success_class = None
        for cls in self.PARSER_CLASSES:
            md = cls()
            try:
                md.from_file(path)
                success_class = cls
                break
            except (ParseError, JSONDecodeError):
                pass
        if success_class:
            self.metadata.metadata = md.metadata
            self.write_metadata(success_class)

    def export_files(self):
        """Export metadata to all supported file formats."""
        for cls in self.PARSER_CLASSES:
            md = cls(self.metadata.metadata)
            fn = self.settings.root_path / cls.XML_FN
            md.to_file(fn)

    def compute_pages_tags(self):
        """Recompute the tag image sizes for ComicRack."""
        with self._get_archive() as archive:
            infolist = archive.infolist()
        parser = ComicInfoXml(self.metadata.metadata)
        parser.compute_pages_tags(infolist)
        self.metadata.metadata["pages"] = parser.metadata.get("pages")

    def rename_file(self):
        """Rename this file according to our favorite naming scheme."""
        md = self.get_metadata()
        name = FilenameMetadata.get_preferred_basename(md)
        new_path = self.path.parent / Path(name + self.path.suffix)
        old_path = self.path
        self.path.rename(new_path)
        print(f"Renamed:\n{old_path} ==> {self.path}")
        self.path = new_path

    def compute_page_count(self):
        """Compute the page count from images in the archive."""
        self.metadata.compute_page_count()
