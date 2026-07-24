"""Methods for extracting files from the archive."""

from collections.abc import Generator, Iterable, Sequence
from pathlib import Path

from loguru import logger

from comicbox._pdf import PAGE_FORMAT_PDF
from comicbox.box.pages.covers import ComicboxPagesCovers
from comicbox.exceptions import ExportError


def _validate_extract_path(path: Path, dest_dir: Path) -> None:
    """Validate that the extract path doesn't escape the destination directory."""
    if not path.resolve().is_relative_to(dest_dir.resolve()):
        reason = f"Unsafe archive path escapes destination: {path}"
        raise ExportError(reason)


class ComicboxExtractPages(ComicboxPagesCovers):
    """Methods for extracting files from the archive."""

    def _extract_page_get_path(self, path: Path, fn: str) -> Path:
        path = path / Path(fn).name if path.is_dir() else path
        if self._archive_is_pdf:
            path = path.with_suffix(self._pdf_suffix)
        return path

    def _extract_page(self, dest_path: Path, fn: str) -> None:
        path = self._extract_page_get_path(dest_path, fn)
        props = {}
        data = self._archive_readfile(fn, props=props)
        if ext := props.get("ext", ""):
            path = path.with_suffix("." + ext)
        dest_dir = dest_path if dest_path.is_dir() else dest_path.parent
        _validate_extract_path(path, dest_dir)
        path.write_bytes(data)

    def _extract_all_pagenames(self, pagenames: Iterable[str], path: Path) -> None:
        success_page_count = 0
        try:
            for fn in pagenames:
                try:
                    self._extract_page(path, fn)
                    success_page_count += 1
                    if not path.is_dir():
                        break
                except Exception as exc:
                    logger.warning(f"Could not extract page {fn}: {exc}")
                    raise
            plural = "s" if success_page_count > 1 else ""
            logger.info(f"Saved {success_page_count} page{plural} to {path}")
        except Exception as exc:
            logger.warning(f"No pages extracted: {exc}")

    def _extract_pagenames_get_path(
        self, pagenames: Sequence[str] | Generator[str], path: Path | str | None
    ) -> Path | None:
        if not pagenames:
            logger.warning("No pages to extract.")
            return None
        if self._config.general.dry_run:
            if isinstance(pagenames, Sequence):
                logger.info(f"Not extracting {len(pagenames)} pages")
            else:
                logger.info("Not extracting pages")
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

    def _extract_pagenames(
        self, pagenames: Generator[str], path: Path | None = None
    ) -> None:
        if path := self._extract_pagenames_get_path(pagenames, path):
            self._extract_all_pagenames(pagenames, path)

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
            logger.warning(f"No pages extracted: {exc}")
        else:
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
        cover_paths_generator = self.generate_cover_paths()
        self._extract_pagenames(cover_paths_generator, path=path)
