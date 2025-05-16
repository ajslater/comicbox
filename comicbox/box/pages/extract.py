"""Methods for extracting files from the archive."""

from pathlib import Path

from loguru import logger

from comicbox.box.archive import archive_close
from comicbox.box.pages.covers import ComicboxPagesCovers


class ComicboxExtractPages(ComicboxPagesCovers):
    """Methods for extracting files from the archive."""

    def _extract_page_get_path(self, path, fn):
        path = path / Path(fn).name if path.is_dir() else path
        if self._archive_is_pdf:
            path = path.with_suffix(self._pdf_suffix)
        return path

    def _extract_page(self, path, fn, *, to_pixmap: bool = False):
        path = self._extract_page_get_path(path, fn)
        with path.open("wb") as page_file:
            data = self._archive_readfile(fn, to_pixmap=to_pixmap)
            page_file.write(data)

    def _extract_all_pagenames(self, pagenames, path):
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

    def _extract_pagenames_get_path(self, pagenames, path):
        if not pagenames:
            logger.warning("No pages to extract.")
            return None
        if self._config.dry_run:
            logger.info(f"Not extracting {len(pagenames)} pages")
            return None

        path = path if path else self._config.dest_path
        return Path(path)

    def _extract_pagenames_to_dir(self, pagenames, path=None):
        if path := self._extract_pagenames_get_path(pagenames, path):
            if not path.is_dir():
                reason = (
                    f"Must extract pages to a directory. {path!s} is not a directory"
                )
                raise ValueError(reason)
            self._extract_all_pagenames(pagenames, path)

    def _extract_pagenames(self, pagenames, path=None):
        if path := self._extract_pagenames_get_path(pagenames, path):
            self._extract_all_pagenames(pagenames, path)

    def _extract_pages(self, page_from=None, page_to=None, path=None):
        pagenames = self.get_pagenames_from(page_from, page_to)
        self._extract_pagenames_to_dir(pagenames, path=path)

    @archive_close
    def extract_pages(self, page_from=None, page_to=None, path=None):
        """Extract pages from archive and write to a path."""
        return self._extract_pages(page_from, page_to, path)

    @archive_close
    def extract_pages_config(self):
        """Extract pages from archive as configured and write to a path."""
        return self._extract_pages(
            self._config.index_from, self._config.index_to, self._config.dest_path
        )

    @archive_close
    def extract_covers(self, path=None):
        """Extract the cover image to a destination file."""
        cover_paths_generator = self.generate_cover_paths()
        self._extract_pagenames(cover_paths_generator, path=path)
