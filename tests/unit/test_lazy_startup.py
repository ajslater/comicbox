"""
Import- and startup-cost contracts.

Each of these guards a deferral that is invisible at runtime: when one
regresses the code still works, it just gets slower again. A module-scope
import added in the wrong place is exactly how they regress, so they are
asserted here rather than left to a benchmark nobody runs.
"""

from __future__ import annotations

import os
import subprocess
import sys
from argparse import Namespace

import pytest

from comicbox.config import get_config
from comicbox.formats import FORMAT_REGISTRATIONS
from comicbox.validate.base import BaseValidator
from comicbox.validate.spec import build_validator

# Importing any of these compiles schemas or drags in a dependency tree
# that only the opt-in --validate path needs.
_VALIDATION_ONLY_PACKAGES = frozenset(
    {
        "elementpath",
        "jsonschema",
        "jsonschema_specifications",
        "referencing",
        "xmlschema",
    }
)


def _modules_loaded_by(code: str) -> set[str]:
    """Run ``code`` in a fresh interpreter and return the modules it left behind."""
    script = code + "\nimport sys\nprint(' '.join(sys.modules))"
    proc = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script], capture_output=True, check=True, text=True
    )
    modules = set(proc.stdout.split())
    assert "comicbox" in modules  # the probe really did import comicbox
    return modules


def test_reading_a_comic_does_not_load_schema_validators() -> None:
    """Importing the box chain must not compile any XSD or JSON Schema."""
    packages = {
        name.split(".")[0] for name in _modules_loaded_by("import comicbox.box")
    }
    assert not packages & _VALIDATION_ONLY_PACKAGES


@pytest.mark.parametrize(
    "code",
    [
        "import comicbox.box",
        "import comicbox.box.online_lookup",
        "from comicbox.cli import main\nmain(('comicbox', '-v'))",
    ],
    ids=["box", "online_lookup", "run"],
)
def test_a_run_never_imports_the_versedb_sdk(code: str) -> None:
    """
    Loading the VerseDB SDK's endpoints costs about 0.8 s (1,011 models).

    Only building a VerseDB client pays it, so neither an offline run nor
    importing the online machinery may.
    """
    modules = _modules_loaded_by(code)
    # The VerseDB format itself was loaded, so the check below means something.
    assert "comicbox.formats.versedb_api" in modules
    assert not {name for name in modules if name.split(".")[0] == "versedb"}


def test_building_the_cli_parser_does_not_build_the_epilog() -> None:
    """The epilog's seven rich Tables are only ever printed by ``--help``."""
    modules = _modules_loaded_by(
        "from comicbox.cli.parser import build_parser\nbuild_parser()"
    )
    assert "comicbox.cli.epilog" not in modules


@pytest.mark.parametrize(
    "code",
    [
        "from comicbox.cli.parser import build_parser\nbuild_parser()",
        "import comicbox.box",
        "from comicbox.cli import main\nmain(('comicbox', '-v'))",
    ],
    ids=["parser", "box", "run"],
)
def test_a_normal_run_does_not_load_the_doctor(code: str) -> None:
    """Only ``comicbox doctor`` pays for the doctor's imports."""
    assert not any(
        name.startswith("comicbox.doctor") for name in _modules_loaded_by(code)
    )


@pytest.mark.parametrize(
    "code",
    [
        "import comicbox.cli",
        "import comicbox.box",
        "from comicbox.cli import main\nmain(('comicbox', '-v'))",
    ],
    ids=["cli", "box", "run"],
)
def test_a_normal_run_does_not_load_reading_lists(code: str) -> None:
    """Only ``comicbox readinglist`` pays for the reading-list imports."""
    assert not any(
        name.startswith("comicbox.readinglists") for name in _modules_loaded_by(code)
    )


# Reading lists are files and pure functions; only the online session,
# which imports these inside its methods, talks to a network.
_NETWORK_PACKAGES = frozenset({"httpx", "mokkari", "requests", "simyan"})


def test_reading_lists_load_no_network_library() -> None:
    packages = {
        name.split(".")[0]
        for name in _modules_loaded_by("import comicbox.readinglists")
    }
    assert "comicbox" in packages
    assert not packages & _NETWORK_PACKAGES


def test_help_still_renders_the_epilog() -> None:
    """Deferring the epilog must not drop it from ``--help``."""
    proc = subprocess.run(
        [sys.executable, "-m", "comicbox.cli", "--help"],
        capture_output=True,
        check=True,
        text=True,
        env={**os.environ, "COLUMNS": "100"},
    )
    assert "--print PHASES" in proc.stdout
    assert "Online sources" in proc.stdout
    assert "Format keys" in proc.stdout


def test_every_registered_validator_spec_builds() -> None:
    """A spec naming a validator comicbox can't build breaks ``--validate``."""
    specs = [
        registration.validator_spec
        for registration in FORMAT_REGISTRATIONS.values()
        if registration.validator_spec is not None
    ]
    assert specs
    for spec in specs:
        assert isinstance(build_validator(spec), BaseValidator)


def test_default_config_is_reused() -> None:
    """The no-args build is memoized, so a per-comic Comicbox stays cheap."""
    assert get_config() is get_config()


def test_default_config_rebuilds_when_the_environment_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A memo outliving its environment would silently ignore env vars."""
    before = get_config()
    monkeypatch.setenv("COMICBOX_ONLINE__LOOKUP__FIRST_WINS", "false")
    after = get_config()
    assert after is not before
    assert after.online.lookup.first_wins is False
    monkeypatch.delenv("COMICBOX_ONLINE__LOOKUP__FIRST_WINS")
    assert get_config().online.lookup.first_wins is True


def test_args_never_come_from_the_memo() -> None:
    """Only the unparameterized build is shared."""
    assert get_config(Namespace(comicbox=Namespace())) is not get_config()
