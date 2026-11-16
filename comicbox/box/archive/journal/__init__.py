"""
Undo an in-place tag write that did not finish.

A re-tag of a CBZ rewrites only its tail: every byte from the first one the
write can change to the end of the file, which holds the trailing tag files,
the central directory and the end record. ``TailJournal`` keeps the old tail
while that happens; if the write raises anything, a keyboard interrupt
included, the tail is written back and the file cut to its old length.

A copy of the tail also goes to a journal beside the archive, complete and
flushed before the archive is touched, and deleted once the write is
flushed. ``replay_journal``, run whenever comicbox opens a comic, settles a
journal a kill left behind (``replay``). The journal is
``.<archive name>.comicbox-journal.tmp``, and a journal being settled
``.<archive name>.comicbox-claimed.tmp``: dot names ending in ``.tmp``,
which a library watcher skips, and never a comic suffix.

A journal holds a marker and version line, a JSON header (the old length, the
tail's offset and checksum, a checksum of the bytes just before the tail, to
show the pages are the ones it was taken from, and the writer's host and
process id), then the tail.
"""

from comicbox.box.archive.journal.record import TAIL_CAP, journal_path
from comicbox.box.archive.journal.replay import replay_journal
from comicbox.box.archive.journal.tail import TailJournal

__all__ = ("TAIL_CAP", "TailJournal", "journal_path", "replay_journal")
