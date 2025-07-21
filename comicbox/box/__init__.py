"""
Comic Archive.

Reads and writes metadata via marshmallow schemas.
Reads and writes archive file data.
"""

from types import MappingProxyType

from loguru import logger

from comicbox.box.print import ComicboxPrint


class Comicbox(
    ComicboxPrint,
):
    """
    Represent a comic archive.

    Contains the compressed archive file and its parsed metadata
    """

    _CONFIG_ACTIONS = MappingProxyType(
        {
            "print": ComicboxPrint.print_out,
            "export": ComicboxPrint.export_files,
            "covers": ComicboxPrint.extract_covers,
        }
    )

    def _run_complex_actions(self):
        noop = True
        if (self._config.index_from, self._config.index_to) != (None, None):
            self.extract_pages_config()
            noop = False
        if self._config.write or self._config.cbz or self._config.delete_all_tags:
            self.dump()
            noop = False
        return noop

    def run(self):
        """Perform archive actions."""
        noop = True
        for attr, method in self._CONFIG_ACTIONS.items():
            if self._config[attr]:
                method(self)
                noop = False
        noop &= self._run_complex_actions()
        if self._config.rename:
            self.rename_file()
            noop = False

        if noop:
            logger.warning("No action performed")
