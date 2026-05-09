"""Pages methods."""

from collections.abc import Iterator

from comicbox.box.archive.filenames import ComicboxArchiveFilenames


class ComicboxArchivePages(ComicboxArchiveFilenames):
    """Pages methods."""

    def get_page_by_filename(
        self, filename: str, pdf_format: str = "", *, hide_text: bool = False
    ) -> bytes:
        """
        Return data for a single page by filename.

        ``hide_text=True`` is forwarded to the PDF backend; non-PDF
        archives ignore it.
        """
        return self._archive_readfile(
            filename, pdf_format=pdf_format, hide_text=hide_text
        )

    def get_pages(
        self,
        page_from: int = 0,
        page_to: int = -1,
        pdf_format: str = "",
        *,
        hide_text: bool = False,
    ) -> Iterator:
        """
        Generate all pages starting with page number.

        ``hide_text=True`` is forwarded to the PDF backend; non-PDF
        archives ignore it.
        """
        if pagenames := self.get_pagenames_from(page_from, page_to):
            for pagename in pagenames:
                yield self._archive_readfile(
                    pagename, pdf_format=pdf_format, hide_text=hide_text
                )

    def get_page_by_index(
        self, index: int, pdf_format: str = "", *, hide_text: bool = False
    ) -> bytes | None:
        """
        Get the page data by index.

        ``hide_text=True`` is forwarded to the PDF backend; non-PDF
        archives ignore it.
        """
        if pages_generator := self.get_pages(
            page_from=index, page_to=index, pdf_format=pdf_format, hide_text=hide_text
        ):
            return next(pages_generator)
        return None
