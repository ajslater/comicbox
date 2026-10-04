"""The doctor's Python packages section: pins come from comicbox's own metadata."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, requires
from typing import TYPE_CHECKING

import pytest

from comicbox.doctor import packages
from comicbox.doctor.context import DoctorContext
from comicbox.doctor.result import CheckResult, Status

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping


@pytest.fixture(autouse=True)
def _fresh_requirements() -> Iterator[None]:
    """Clear the parsed requirements, which are cached per process."""
    packages._requirements.cache_clear()
    yield
    packages._requirements.cache_clear()


def _fake_metadata(
    monkeypatch: pytest.MonkeyPatch,
    requirements: list[str],
    installed: Mapping[str, str],
) -> None:
    monkeypatch.setattr(packages, "requires", lambda _name: requirements)

    def version(name: str) -> str:
        if name not in installed:
            raise PackageNotFoundError(name)
        return installed[name]

    monkeypatch.setattr(packages, "version", version)


def _rows(
    monkeypatch: pytest.MonkeyPatch,
    requirements: list[str],
    installed: Mapping[str, str],
) -> list[CheckResult]:
    _fake_metadata(monkeypatch, requirements, installed)
    return list(packages.check_requirements(DoctorContext()))


def test_real_requirements_come_from_metadata() -> None:
    """The dev venv's editable install carries the metadata too."""
    rows = list(packages.check_requirements(DoctorContext()))
    assert [row.status for row in rows] == [Status.OK]
    # Every base requirement, and not the pdf extra.
    base = [raw for raw in requires("comicbox") or () if "extra ==" not in raw]
    assert rows[0].detail == f"{len(base)} satisfied"


def test_missing_metadata_is_one_warn_row(monkeypatch: pytest.MonkeyPatch) -> None:
    def requires(name: str) -> list[str]:
        raise PackageNotFoundError(name)

    monkeypatch.setattr(packages, "requires", requires)
    rows = list(packages.check_requirements(DoctorContext()))
    assert len(rows) == 1
    assert rows[0].status is Status.WARN
    assert "metadata unavailable" in rows[0].detail


def test_ok_missing_and_wrong_version(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = _rows(
        monkeypatch,
        ["good~=1.0", "gone>=2", "old~=4.2"],
        {"good": "1.3", "old": "4.1.0"},
    )
    by_name = {row.name: row for row in rows}
    assert by_name["gone"].status is Status.MISSING
    assert by_name["gone"].fix == "pip install 'gone>=2'"
    assert by_name["old"].status is Status.WRONG_VERSION
    assert by_name["old"].found == "4.1.0"
    assert by_name["old"].detail == "comicbox requires old~=4.2"
    assert by_name["requirements"].status is Status.OK
    assert by_name["requirements"].detail == "1 satisfied"


def test_prerelease_satisfies_its_pin(monkeypatch: pytest.MonkeyPatch) -> None:
    """A dev build of a dependency must not read as the wrong version."""
    rows = _rows(monkeypatch, ["lib~=4.2"], {"lib": "4.3.0rc1"})
    assert [row.status for row in rows] == [Status.OK]


def test_markers_skip_extras_and_other_platforms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The PDF extra belongs to the PDF row, and a false marker isn't required."""
    rows = _rows(
        monkeypatch,
        [
            "base>=1",
            'comicbox-pdffile~=1.0; extra == "pdf"',
            'ancient>=1; python_version < "3.0"',
        ],
        {"base": "1.0"},
    )
    assert [(row.name, row.status) for row in rows] == [("requirements", Status.OK)]
    assert rows[0].detail == "1 satisfied"


def test_pinned_names_the_pin(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_metadata(monkeypatch, ["py7zr~=1.1.0", "Pillow>=12"], {})
    assert packages.pinned("py7zr") == "py7zr~=1.1.0"
    assert packages.pinned("pillow") == "Pillow>=12"
    assert packages.pinned("unknown") == "unknown"
    assert packages.reinstall_hint("py7zr") == (
        "pip install --force-reinstall 'py7zr~=1.1.0'"
    )


def test_host_header_names_comicbox_and_python() -> None:
    header = packages.host_header()
    assert header[0].startswith("comicbox ")
    assert header[1].startswith("Python ")
