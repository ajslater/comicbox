"""
Comic Archive.

Reads and writes metadata via marshmallow schemas.
Reads and writes archive file data.
"""

from collections.abc import Callable
from types import MappingProxyType

from loguru import logger

from comicbox.box.print import ComicboxPrint
from comicbox.config.settings import ComicboxSettings


class Comicbox(
    ComicboxPrint,
):
    """
    Represent a comic archive.

    Contains the compressed archive file and its parsed metadata
    """

    # Each entry: action name → (predicate over settings, bound method to invoke).
    _CONFIG_ACTIONS: MappingProxyType[
        str, tuple[Callable[[ComicboxSettings], object], Callable[..., object]]
    ] = MappingProxyType(
        {
            "print": (lambda s: bool(s.print.phases), ComicboxPrint.print_out),
            "validate": (lambda s: s.print.validate, ComicboxPrint.validate),
            "export": (
                lambda s: bool(s.convert.export_formats),
                ComicboxPrint.export_files,
            ),
            "covers": (
                lambda s: bool(s.convert.extract_covers),
                ComicboxPrint.extract_covers,
            ),
        }
    )

    def _run_complex_actions(self) -> bool:
        noop = True
        convert = self._config.convert
        write = self._config.write
        if (convert.extract_pages_from, convert.extract_pages_to) != (None, None):
            self.extract_pages_config()
            noop = False
        if write.formats or convert.cbz or write.delete_all_tags:
            self.dump()
            noop = False
        return noop

    def run(self) -> None:
        """Perform archive actions."""
        # Run online lookup before any action runs so all phases (print,
        # validate, export, write, …) see a consistent post-online state.
        # Lookup is gated on `online.enabled` and idempotent, so this is a
        # no-op when --online wasn't passed.
        self.run_online_lookup()

        noop = True
        for predicate, method in self._CONFIG_ACTIONS.values():
            if predicate(self._config):
                method(self)
                noop = False
        noop &= self._run_complex_actions()
        if self._config.convert.rename:
            self.rename_file()
            noop = False

        if noop:
            logger.warning("No action performed")
