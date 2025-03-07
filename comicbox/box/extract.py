"""Methods for extracting files from the archive."""

from logging import INFO, getLogger
from pathlib import Path

from comicbox.box.archive import archive_close
from comicbox.box.pages import ComicboxPagesMixin

LOG = getLogger(__name__)


class ComicboxExtractMixin(ComicboxPagesMixin):
    """Methods for extracting files from the archive."""

    def _extract_page(self, path, fn, to_pixmap: bool):
        path = path / Path(fn).name if path.is_dir() else path
        if self._archive_is_pdf:
            path = path.with_suffix(self._pdf_suffix)
        with path.open("wb") as page_file:
            data = self._archive_readfile(fn, to_pixmap)
            page_file.write(data)

    def _extract_all_pagenames(self, pagenames, path):
        success_page_count = 0
        try:
            for fn in pagenames:
                try:
                    self._extract_page(path, fn, to_pixmap=False)
                    success_page_count += 1
                    if not path.is_dir():
                        break
                except Exception as exc:
                    LOG.warning(f"Could not extract page {fn}: {exc}")
                    raise
            if LOG.isEnabledFor(INFO):
                plural = "s" if success_page_count > 1 else ""
                LOG.info(f"Saved {success_page_count} page{plural} to {path}")
        except Exception as exc:
            LOG.warning(f"No pages extracted: {exc}")

    def _extract_pagenames(self, pagenames, check_path_is_dir: bool, path=None):
        if not pagenames:
            LOG.warning("No pages to extract.")
            return
        if self._config.dry_run:
            LOG.info(f"Not extracting {len(pagenames)} pages")
            return

        path = path if path else self._config.dest_path
        path = Path(path)

        if check_path_is_dir and not path.is_dir():
            reason = f"Must extract pages to a directory. {path!s} is not a directory"
            raise ValueError(reason)

        self._extract_all_pagenames(pagenames, path)

    @archive_close
    def extract_pages(self, page_from=None, page_to=None, path=None):
        """Extract pages from archive and write to a path."""
        pagenames = self.get_pagenames_from(page_from, page_to)
        self._extract_pagenames(pagenames, check_path_is_dir=True, path=path)

    @archive_close
    def extract_cover_as(self, path=None):
        """Extract the cover image to a destination file."""
        pagenames = self.get_cover_path_list()

        self._extract_pagenames(pagenames, check_path_is_dir=False, path=path)
