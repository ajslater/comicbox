"""
The no-path guard must fire for a pre-built ``ComicboxSettings`` too.

``post_process_set_for_path`` turns off the options that need an archive
(cbz, rename, page/cover extraction, writes, the file-type/file-names
print phases) and warns once, so a pathless run ends with a readable
message instead of an exception from deep inside the archive layer.

It was dead for every CLI run. ``Runner`` builds one ``ComicboxSettings``
and hands the same object to each ``Comicbox``, and ``Comicbox.__init__``
short-circuited on ``isinstance(config, ComicboxSettings)`` — skipping
``get_config``, and with it the guard. Only the Namespace/Mapping
constructor paths (i.e. tests and library callers) ever saw it. So
``comicbox --rename`` with no path raised ArchiveWriteError with a
traceback rather than warning that rename needs a file.
"""

from __future__ import annotations

from argparse import Namespace

from comicbox import cli
from comicbox.box import Comicbox
from comicbox.config import get_config
from comicbox.print import PrintPhases
from tests.const import CIX_CBZ_SOURCE_PATH


def _settings(**convert: object):
    """Build real settings for a pathless run with convert actions on."""
    return get_config(Namespace(comicbox=Namespace(convert=Namespace(**convert))))


def test_prebuilt_settings_still_hit_the_guard() -> None:
    """A ComicboxSettings passed straight in must be path-post-processed."""
    settings = _settings(rename=True, cbz=True)
    # Sanity: the guard hasn't fired yet — get_config's box=False default
    # leaves the actions on for a Runner that hasn't picked a file.
    assert settings.convert.rename is True
    assert settings.convert.cbz is True

    with Comicbox(None, config=settings) as car:
        assert car._config.convert.rename is False
        assert car._config.convert.cbz is False


def test_guard_leaves_settings_alone_when_a_path_is_present() -> None:
    """With a real archive the actions must survive untouched."""
    settings = _settings(cbz=True)
    with Comicbox(CIX_CBZ_SOURCE_PATH, config=settings) as car:
        assert car._config.convert.cbz is True


def test_pathless_print_phases_are_dropped() -> None:
    """file-type / file-names can't be printed without a file."""
    settings = get_config(Namespace(comicbox=Namespace(print=Namespace(phases="tfp"))))
    assert PrintPhases.FILE_TYPE in settings.print.phases

    with Comicbox(None, config=settings) as car:
        phases = car._config.print.phases
        assert PrintPhases.FILE_TYPE not in phases
        assert PrintPhases.FILE_NAMES not in phases
        # The metadata phase doesn't need a file, so it stays.
        assert PrintPhases.METADATA in phases


def test_pathless_cli_run_warns_instead_of_raising() -> None:
    """
    End-to-end: the CLI path that used to traceback now warns.

    ``comicbox --rename`` with no paths reached ``rename_file()`` and
    raised ArchiveWriteError. Nothing in the serial run loop catches it,
    so the user got a stack trace for a plain usage mistake.
    """
    cli.main(("comicbox", "--rename", "--cbz"))  # must not raise
