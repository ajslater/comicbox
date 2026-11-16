"""
What opening a comic does with a journal beside it.

A journal in flight refuses the comic. A stale one is claimed, by an atomic
rename, so one process at a time settles it, and then: one that is not valid
is deleted, since the archive was never touched under it; a valid one beside
an archive that verifies is deleted and the comic left as it is; a valid one
beside a damaged archive is replayed when the bytes before its tail are the
archive's, and otherwise both are left alone. A dry run settles nothing.
"""

from __future__ import annotations

import os
from contextlib import suppress
from enum import Enum
from typing import TYPE_CHECKING

from loguru import logger

from comicbox.box.archive.journal.record import (
    Found,
    claimed_path,
    in_flight,
    is_valid,
    is_young,
    journal_path,
    owes_rollback,
    read_journal,
    restore,
)
from comicbox.box.archive.journal.verify import fits, verifies
from comicbox.exceptions import DestinationOccupiedError, UnfinishedWriteError

if TYPE_CHECKING:
    from pathlib import Path


class _Verdict(Enum):
    """What a stale journal calls for."""

    INCOMPLETE = "remove it: it was never complete"
    INCOMPLETE_DAMAGED = "remove it: it was never complete, and the comic is damaged"
    WHOLE = "remove it: the comic is whole"
    REPLAY = "undo the interrupted write"
    UNFIT = "leave it and the comic alone: it does not fit the comic"


def _judge(path: Path, found: Found) -> _Verdict:
    whole = verifies(path)
    if not is_valid(found) or found.header is None:
        return _Verdict.INCOMPLETE if whole else _Verdict.INCOMPLETE_DAMAGED
    if whole and not owes_rollback(found):
        # One that owes a rollback is replayed even so: a failed write can
        # leave an archive that verifies, missing what it did not finish.
        return _Verdict.WHOLE
    return _Verdict.REPLAY if fits(path, found.header) else _Verdict.UNFIT


def _in_progress(path: Path) -> DestinationOccupiedError:
    return DestinationOccupiedError(path, path, "writing")


def _give_back(journal: Path, claimed: Path) -> None:
    """Return a claimed journal to its name, unless a journal is there now."""
    with suppress(OSError):
        os.link(claimed, journal)
        claimed.unlink()


def _take_over(path: Path, journal: Path, claimed: Path, *, dry_run: bool) -> None:
    """
    Meet a claimed journal: a write in progress, unless its claimer died.

    A claim under five minutes old is a process settling the journal now.
    An older one is given back to its name, to be settled as any stale
    journal; a link, which fails when a journal is already there, makes
    that safe against a second process doing the same.
    """
    if (found := read_journal(claimed, path)) is None:
        return
    if is_young(found):
        raise _in_progress(path)
    if dry_run:
        logger.info(f"{path}: would take over {claimed.name}, abandoned.")
        return
    try:
        os.link(claimed, journal)
    except OSError as exc:
        logger.warning(
            f"{path}: {claimed.name} was abandoned and cannot be taken over: {exc}"
        )
        raise _in_progress(path) from exc
    with suppress(OSError):
        claimed.unlink()


def _claim(path: Path, journal: Path, claimed: Path, found: Found) -> Found | None:
    """
    Claim a stale journal by renaming it; None where the directory forbids it.

    It is dated now first, so the claim is young from the moment it exists.
    A process that loses the claim, or finds that what it claimed is not the
    journal it judged, as when another settled that one and began a write,
    treats the comic as having a write in progress.
    """
    try:
        os.utime(journal)
        journal.rename(claimed)
    except FileNotFoundError:
        raise _in_progress(path) from None
    except OSError:
        return None
    if (mine := read_journal(claimed, path)) is None or mine.data != found.data:
        if mine is not None:
            _give_back(journal, claimed)
        raise _in_progress(path)
    return mine


def _remove(path: Path, claimed: Path) -> None:
    try:
        claimed.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning(f"{path}: cannot remove {claimed.name}: {exc}")


def _unrepairable(path: Path, why: str) -> UnfinishedWriteError:
    reason = (
        f"{path} was damaged by an interrupted write and cannot be repaired here: {why}"
    )
    return UnfinishedWriteError(reason)


def _settle_unclaimed(path: Path, journal: Path, found: Found) -> None:
    """Settle a stale journal the directory will not let this process claim."""
    verdict = _judge(path, found)
    if verdict in (_Verdict.WHOLE, _Verdict.INCOMPLETE):
        logger.warning(f"{path}: cannot remove {journal.name}, a finished journal.")
        return
    if verdict is _Verdict.UNFIT:
        logger.warning(
            f"{path}: {journal.name} does not fit the comic; both left alone."
        )
        return
    raise _unrepairable(path, "its directory is read-only")


def _settle(path: Path, journal: Path, claimed: Path, found: Found) -> bool:
    """Act on a claimed stale journal; whether the comic was restored."""
    verdict = _judge(path, found)
    if verdict is _Verdict.UNFIT:
        _give_back(journal, claimed)
        logger.warning(
            f"{path}: {journal.name} does not fit the comic; both left alone."
        )
        return False
    if verdict is _Verdict.REPLAY and found.header is not None:
        header = found.header
        try:
            restore(path, header.offset, found.tail, header.length)
        except OSError as exc:
            _give_back(journal, claimed)
            raise _unrepairable(path, str(exc)) from exc
        logger.warning(f"{path}: undid a write that was interrupted.")
    elif verdict is _Verdict.INCOMPLETE_DAMAGED:
        logger.warning(
            f"{path}: is damaged, and {journal.name} is incomplete; removed it."
        )
    _remove(path, claimed)
    return verdict is _Verdict.REPLAY


def replay_journal(path: Path, *, dry_run: bool = False) -> bool:
    """
    Settle a journal beside a comic before it is read; whether it restored it.

    Looking costs a failed open of each name, and never fails the open by
    itself. A journal in flight refuses the comic for reading and writing.
    """
    journal = journal_path(path)
    claimed = claimed_path(journal)
    _take_over(path, journal, claimed, dry_run=dry_run)
    if (found := read_journal(journal, path)) is None:
        return False
    if in_flight(journal, found):
        raise _in_progress(path)
    if dry_run:
        logger.info(f"{path}: would {_judge(path, found).value} ({journal.name}).")
        return False
    if (mine := _claim(path, journal, claimed, found)) is None:
        _settle_unclaimed(path, journal, found)
        return False
    return _settle(path, journal, claimed, mine)
