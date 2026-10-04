"""State the doctor's checks share, and the shape of a check."""

from __future__ import annotations

from argparse import Namespace
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from comicbox.config.settings import ComicboxSettings
    from comicbox.doctor.result import CheckResult


@dataclass
class DoctorContext:
    """
    What the checks run against.

    ``args`` is the same ``Namespace(comicbox=...)`` a run would get, so
    the doctor diagnoses the config that run would see. The Config
    section's validation check fills in ``settings``; it stays None when
    the config doesn't load, and the checks after it say so.
    """

    args: Namespace = field(default_factory=lambda: Namespace(comicbox=Namespace()))
    #: Sources to verify with one live request each; "all" means every
    #: configured one. Empty keeps the doctor offline.
    online_sources: tuple[str, ...] = ()
    settings: ComicboxSettings | None = None

    @property
    def cns(self) -> Any:
        """The inner comicbox namespace the CLI parsed."""
        return getattr(self.args, "comicbox", self.args)


#: (section, check name, check). The name labels the ERROR row the runner
#: reports when the check itself crashes.
Check = tuple[str, str, "Callable[[DoctorContext], Iterable[CheckResult]]"]
