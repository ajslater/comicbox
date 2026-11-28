"""
PDF author export takes every writing credit.

The author role set was built from enum values as spelled ("Plot", "Story",
"Translator", "Author") but compared with lowercased role names, so only the
roles already spelled in lowercase reached the PDF author field.
"""

from __future__ import annotations

from comicbox.box import Comicbox
from comicbox.formats import MetadataFormats
from comicbox.formats.pdf.transform.credits import _credits_to_authors


def test_every_writing_role_is_an_author() -> None:
    """Script, Plot, Story, Translator, Writer and Author all export."""
    credits_ = {
        name: {"roles": {role: {}}}
        for name, role in (
            ("A", "Script"),
            ("B", "Plot"),
            ("C", "Story"),
            ("D", "Translator"),
            ("E", "Writer"),
            ("F", "Author"),
        )
    }
    assert _credits_to_authors(credits_) == {"A", "B", "C", "D", "E", "F"}


def test_non_writing_role_is_not_an_author() -> None:
    """An artist is not exported as an author."""
    assert not _credits_to_authors({"G": {"roles": {"Penciller": {}}}})


def test_metroninfo_plot_credit_reaches_pdf_author() -> None:
    """A MetronInfo Plot credit lands in the PDF author field."""
    xml = (
        "<MetronInfo><Credits><Credit><Creator>Plotter</Creator>"
        "<Roles><Role>Plot</Role></Roles></Credit></Credits></MetronInfo>"
    )
    with Comicbox() as car:
        car.add_metadata(xml, MetadataFormats.METRON_INFO)
        written = car.to_string(MetadataFormats.PDF)
    assert "Plotter" in written
