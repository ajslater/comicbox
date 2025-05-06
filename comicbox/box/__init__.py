"""
Comic Archive.

Reads and writes metadata via marshmallow schemas.
Reads and writes archive file data.
"""

from logging import getLogger
from types import MappingProxyType

from comicbox.box.print import ComicboxPrint
from comicbox.print import PrintPhases

LOG = getLogger(__name__)


_NO_PATH_ATTRS = MappingProxyType(
    {
        "index_from": None,
        "index_to": None,
        "write": None,
        "covers": False,
        "cbz": False,
        "delete_all_tags": False,
        "rename": False,
    }
)
_NO_PATH_PRINT_PHASES = (PrintPhases.FILE_TYPE, PrintPhases.FILE_NAMES)


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

    def _config_for_no_path(self):
        """Turn off options and warn if no path."""
        need_file_opts = []

        for phase in _NO_PATH_PRINT_PHASES:
            if phase in self._config.print:
                need_file_opts.append(f"print {phase.name.lower()}")
                self._config.print = frozenset(self._config.print - {phase})

        for attr, val in _NO_PATH_ATTRS.items():
            if self._config[attr]:
                need_file_opts.append(attr)
                self._config[attr] = val

        if need_file_opts:
            plural = "s" if len(need_file_opts) > 1 else ""
            opts = ", ".join(need_file_opts)
            LOG.warning(
                f"Cannot perform action{plural} '{opts}' without an archive path."
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
        if not self._path:
            self._config_for_no_path()

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
            LOG.warning("No action performed")
