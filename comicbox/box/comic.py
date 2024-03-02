"""Comic Archive.

Reads and writes metadata via marshmallow schemas.
Reads and writes file data via ZipFile/RarFile etc.
"""

from logging import getLogger

from comicbox.box.extract import ComicboxExtractMixin
from comicbox.box.print import ComicboxPrintMixin
from comicbox.box.write import ComicboxWriteMixin
from comicbox.print import PrintPhases

LOG = getLogger(__name__)


class Comicbox(
    ComicboxPrintMixin,
    ComicboxWriteMixin,
    ComicboxExtractMixin,
):
    """Represent a comic archive.

    Contains the compressed archive file and its parsed metadata
    """

    def _config_for_no_path(self):  # noqa:C901
        """Turn off options and warn if no path."""
        need_file_opts = []

        if PrintPhases.FILE_TYPE in self._config.print:
            need_file_opts += ["print file_type"]
            self._config.print = frozenset(self._config.print - {PrintPhases.FILE_TYPE})
        if PrintPhases.FILE_NAMES in self._config.print:
            need_file_opts += ["print file_names"]
            self._config.print = frozenset(
                self._config.print - {PrintPhases.FILE_NAMES}
            )
        if self._config.cover:
            need_file_opts += ["covers"]
            self._config.cover = False
        if self._config.index_from:
            need_file_opts += ["index_from"]
            self._config.index_from = None
        if self._config.index_to:
            need_file_opts += ["index_to"]
            self._config.index_to = None
        if self._config.write:
            need_file_opts += ["write"]
            self._config.write = None
        if self._config.cbz:
            need_file_opts += ["cbz"]
            self._config.cbz = False
        if self._config.delete:
            need_file_opts += ["delete"]
            self._config.delete = False
        if self._config.rename:
            need_file_opts += ["rename"]
            self._config.rename = False

        if need_file_opts:
            plural = "s" if len(need_file_opts) > 1 else ""
            opts = ", ".join(need_file_opts)
            LOG.warning(
                f"Cannot perform action{plural} '{opts}' without an archive path."
            )

    def run(self):  # C901
        """Perform archive actions."""
        if not self._path:
            self._config_for_no_path()

        noop = True
        if self._config.print:
            self.print_out()
            noop = False
        if self._config.export:
            self.export_files()
            noop = False
        if self._config.cover:
            self.extract_cover_as()
            noop = False
        if (self._config.index_from, self._config.index_to) != (None, None):
            self.extract_pages(
                self._config.index_from, self._config.index_to, self._config.dest_path
            )
            noop = False
        if self._config.write or self._config.cbz or self._config.delete:
            self.write()
            noop = False
        if self._config.rename:
            self.rename_file()
            noop = False

        if noop:
            LOG.warning("No action performed")
