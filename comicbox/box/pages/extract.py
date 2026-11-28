"""Methods for extracting files from the archive."""

import threading
import unicodedata
from collections.abc import Iterable, Sequence
from pathlib import Path

from loguru import logger

from comicbox._pdf import PAGE_FORMAT_PDF
from comicbox.box.pages.covers import ComicboxPagesCovers
from comicbox.exceptions import ExportError, UnsupportedArchiveTypeError

#: A PDF's leading bytes, for when comicbox runs without PDF support.
_PDF_MAGIC = b"%PDF"


def _is_pdf_by_magic(path: Path) -> bool:
    try:
        with path.open("rb") as file:
            return file.read(len(_PDF_MAGIC)) == _PDF_MAGIC
    except OSError:
        return False


class CoverDestinations:
    """The cover files one run has written, shared by its workers."""

    def __init__(self) -> None:
        """Start with none."""
        self._paths: set[Path] = set()
        self._lock = threading.Lock()

    def claim(self, path: Path) -> None:
        """Take a cover file for this run, refusing one another comic took."""
        key = path.resolve()
        with self._lock:
            if key in self._paths:
                reason = (
                    f"{path}: another comic's cover in this run went there:"
                    " not overwritten."
                )
                raise ExportError(reason)
            self._paths.add(key)

    def release(self, path: Path) -> None:
        """Give a cover file back: nothing was written to it after all."""
        with self._lock:
            self._paths.discard(path.resolve())


def _fold(name: str) -> str:
    """Fold a name as a case-insensitive, normalizing disk does."""
    return unicodedata.normalize("NFC", name).casefold()


def _validate_extract_path(path: Path, dest_dir: Path) -> None:
    """Validate that the extract path doesn't escape the destination directory."""
    if not path.resolve().is_relative_to(dest_dir.resolve()):
        reason = f"Unsafe archive path escapes destination: {path}"
        raise ExportError(reason)


class _PageNames:
    """
    The names one extraction to a directory gives its pages, none shared.

    Every page's own base name is reserved, before the first write, for
    the first page that has it. A later page of that name is saved as its
    page index, zero-padded to the digits of the page count as a PDF's page
    names are, a hyphen and the name (``05-01.jpg``); while that is still
    reserved or given, the prefix is added again (``05-05-01.jpg``), so a
    real page never loses its name to a made one. Names are compared folded,
    as a case-insensitive disk sees them, and pages go in page order, so
    the names are the same on every disk and every run.
    """

    def __init__(self, pagenames: Sequence[str], all_pagenames: Sequence[str]) -> None:
        """Reserve each page's own name for the first page that has it."""
        self._owners: dict[str, str] = {}
        for fn in pagenames:
            self._owners.setdefault(_fold(Path(fn).name), fn)
        self._given: set[str] = set()
        self._index = {fn: index for index, fn in enumerate(all_pagenames)}
        self._width = len(str(len(all_pagenames)))

    def _free(self, key: str, fn: str) -> bool:
        return self._owners.get(key, fn) == fn and key not in self._given

    def name(self, fn: str, name: str) -> str:
        """Give a page its name, or its index-prefixed name if that is taken."""
        if not self._free(_fold(name), fn):
            prefix = f"{self._index[fn]:0{self._width}}-"
            name = prefix + name
            while _fold(name) in self._owners or _fold(name) in self._given:
                name = prefix + name
        self._given.add(_fold(name))
        return name


class ComicboxExtractPages(ComicboxPagesCovers):
    """Methods for extracting files from the archive."""

    #: Set by the Runner, so two comics' covers never share one file.
    _cover_destinations: CoverDestinations | None = None

    def set_cover_destinations(self, destinations: CoverDestinations | None) -> None:
        """Register the run's record of the cover files it has written."""
        self._cover_destinations = destinations

    def _is_comic_file(self, path: Path) -> bool:
        """
        Tell a comic as opening one does: by its bytes, not its name.

        Opening sniffs the archive type and reads nothing more. A file
        with a comic's suffix that is no archive is no comic. A PDF is one
        even where comicbox runs without PDF support and cannot open it.
        """
        try:
            with type(self)(path, config=self._config):
                return True
        except UnsupportedArchiveTypeError:
            return _is_pdf_by_magic(path)

    def _refuse_cover_destination(self, path: Path) -> CoverDestinations | None:
        """
        Refuse a file that is a comic, or that another comic's cover took.

        A cover's path, in a directory or named by -d, is refused when a file
        there opens as an archive, or when another comic's cover in this run
        went there. Returns the run's record when this cover claimed the path.
        """
        if path.is_file() and self._is_comic_file(path):
            reason = f"{path} is a comic or PDF: not overwritten with a page."
            raise ExportError(reason)
        if claims := self._cover_destinations:
            claims.claim(path)
        return claims

    def _extract_page_get_path(self, path: Path, fn: str) -> Path:
        path = path / Path(fn).name if path.is_dir() else path
        if self._archive_is_pdf:
            path = path.with_suffix(self._pdf_suffix)
        return path

    def _extract_page(
        self,
        dest_path: Path,
        fn: str,
        names: _PageNames | None = None,
        *,
        cover: bool = False,
    ) -> None:
        path = self._extract_page_get_path(dest_path, fn)
        props = {}
        data = self._archive_readfile(fn, props=props)
        if ext := props.get("ext", ""):
            path = path.with_suffix("." + ext)
        claims = None
        if dest_path.is_dir():
            dest_dir = dest_path
            if names is not None:
                path = path.with_name(names.name(fn, path.name))
        else:
            dest_dir = dest_path.parent
        if cover:
            # In a directory too: two comics' covers of one name are one file.
            claims = self._refuse_cover_destination(path)
        try:
            _validate_extract_path(path, dest_dir)
            path.write_bytes(data)
        except BaseException:
            if claims:
                claims.release(path)
            raise

    def _extract_all_pagenames(
        self, pagenames: Iterable[str], path: Path, *, cover: bool = False
    ) -> None:
        names = None
        if path.is_dir():
            pagenames = tuple(pagenames)
            names = _PageNames(pagenames, self.get_page_filenames())
            # Every page, so a 7z is decompressed in batches, not once a page.
            pagenames = self._iter_prefetched(pagenames)
        success_page_count = 0
        try:
            # The prefetch reads in the loop, so it is guarded too.
            for fn in pagenames:
                self._extract_page(path, fn, names, cover=cover)
                success_page_count += 1
                if not path.is_dir():
                    break
        except Exception as exc:
            reason = (
                f"Could not extract pages to {path}"
                f" after saving {success_page_count}: {exc}"
            )
            raise ExportError(reason) from exc
        plural = "s" if success_page_count > 1 else ""
        logger.info(f"Saved {success_page_count} page{plural} to {path}")

    def _extract_pagenames_get_path(
        self, pagenames: Sequence[str], path: Path | str | None
    ) -> Path | None:
        if not pagenames:
            logger.warning("No pages to extract.")
            return None
        if self._config.general.dry_run:
            logger.info(f"Not extracting {len(pagenames)} pages")
            return None

        resolved_path = path or self._config.general.dest_path
        return Path(resolved_path)

    def _extract_pagenames_get_dir(
        self, pagenames: Sequence[str], path: Path | str | None
    ) -> Path | None:
        resolved_path = self._extract_pagenames_get_path(pagenames, path)
        if resolved_path and not resolved_path.is_dir():
            reason = (
                f"Must extract pages to a directory. {resolved_path!s} "
                "is not a directory"
            )
            raise ExportError(reason)
        return resolved_path

    def _extract_pagenames_to_dir(
        self, pagenames: tuple[str, ...], path: Path | str | None = None
    ) -> None:
        if resolved_path := self._extract_pagenames_get_dir(pagenames, path):
            self._extract_all_pagenames(pagenames, resolved_path)

    def _extract_cover_pagenames(
        self, pagenames: Sequence[str], path: Path | None = None
    ) -> None:
        if path := self._extract_pagenames_get_path(pagenames, path):
            self._extract_all_pagenames(pagenames, path, cover=True)

    def _is_pdf_range_mode(self) -> bool:
        """Are pdf pages extracted as pdfs, which merge into one document."""
        return (
            self._archive_is_pdf
            and self._get_pdf_format(default=PAGE_FORMAT_PDF) == PAGE_FORMAT_PDF
        )

    def _extract_pdf_range_to_dir(
        self, pagenames: tuple[str, ...], path: Path | str | None
    ) -> None:
        """Extract a range of pdf pages as one pdf."""
        resolved_path = self._extract_pagenames_get_dir(pagenames, path)
        if not resolved_path:
            return
        # PDF page names are contiguous zero padded indexes (embedded files are
        # filtered out of the page list), so the range is their first and last.
        page_path = resolved_path / f"{pagenames[0]}-{pagenames[-1]}{self._pdf_suffix}"
        try:
            props = {}
            data = self._archive_read_pdf_range(
                int(pagenames[0]), int(pagenames[-1]), props=props
            )
            if ext := props.get("ext", ""):
                page_path = page_path.with_suffix("." + ext)
            _validate_extract_path(page_path, resolved_path)
            page_path.write_bytes(data)
        except Exception as exc:
            reason = f"No pages extracted: {exc}"
            raise ExportError(reason) from exc
        logger.info(f"Saved {len(pagenames)} pages to {page_path}")

    def extract_pages(
        self,
        page_from: int | None = None,
        page_to: int | None = None,
        path: Path | str | None = None,
    ) -> None:
        """Extract pages from archive and write to a path."""
        pagenames = self.get_pagenames_from(page_from, page_to)
        if len(pagenames) > 1 and self._is_pdf_range_mode():
            self._extract_pdf_range_to_dir(pagenames, path)
        else:
            self._extract_pagenames_to_dir(pagenames, path=path)

    def extract_pages_config(self) -> None:
        """Extract pages from archive as configured and write to a path."""
        convert = self._config.convert
        return self.extract_pages(
            convert.extract_pages_from,
            convert.extract_pages_to,
            self._config.general.dest_path,
        )

    def extract_covers(self, path: Path | None = None) -> None:
        """Extract the cover image to a destination file."""
        self._extract_cover_pagenames(self.get_cover_paths(), path=path)
