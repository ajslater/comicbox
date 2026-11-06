#!/usr/bin/env python3
"""Render comicbox's XML schemas as markdown pages for the docs site."""

import re
from collections.abc import Iterable, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import Final
from xml.etree import ElementTree as ET

import xmlschema
from xmlschema.names import XSD_NAMESPACE
from xmlschema.validators import (
    XsdAtomicRestriction,
    XsdComplexType,
    XsdFacet,
    XsdGroup,
    XsdList,
    XsdType,
)

ROOT: Final = Path(__file__).resolve().parent.parent
SCHEMAS_DIR: Final = ROOT / "comicbox" / "schemas"
DEST: Final = ROOT / "docs" / "schema"
SOURCE_URL: Final = "https://github.com/ajslater/comicbox/blob/main/schemas/"
XS: Final = f"{{{XSD_NAMESPACE}}}"
TYPE_TAGS: Final = frozenset({f"{XS}complexType", f"{XS}simpleType"})
# The XSDs' own section headings. Each page has its own sections instead.
SECTION_HEADINGS: Final = frozenset({"Complex Types", "Simple Types"})
MODEL_INTROS: Final = MappingProxyType(
    {
        "all": "Child elements, in any order:",
        "choice": "One of these child elements:",
        "sequence": "Child elements, in this order:",
    }
)
FACET_LABELS: Final = MappingProxyType(
    {
        f"{XS}fractionDigits": "Fraction digits",
        f"{XS}length": "Length",
        f"{XS}maxExclusive": "Less than",
        f"{XS}maxInclusive": "Maximum",
        f"{XS}maxLength": "Maximum length",
        f"{XS}minExclusive": "Greater than",
        f"{XS}minInclusive": "Minimum",
        f"{XS}minLength": "Minimum length",
        f"{XS}totalDigits": "Total digits",
    }
)

NoteKey = tuple[str, str, str]
Notes = dict[NoteKey, str]


def _squash(text: str | None) -> str:
    """Collapse runs of whitespace, as in a multi-line comment or assert."""
    return " ".join((text or "").split())


def _note_key(node: ET.Element, type_name: str) -> NoteKey | None:
    """Name the schema component a comment describes."""
    tag = node.tag
    if tag in TYPE_TAGS:
        return ("type", node.get("name", ""), "")
    if tag in (f"{XS}element", f"{XS}attribute"):
        return (tag.removeprefix(XS), type_name, node.get("name", ""))
    if tag == f"{XS}enumeration":
        return ("enumeration", type_name, node.get("value", ""))
    if tag == f"{XS}assert":
        return ("assert", type_name, _squash(node.get("test")))
    return None


def _comment_target(children: Sequence[ET.Element], index: int) -> ET.Element | None:
    """
    Find the node a comment describes.

    A comment on the same line as the node before it annotates that node. A
    comment on its own line introduces the node after it.
    """
    if index and "\n" not in (children[index - 1].tail or ""):
        return children[index - 1]
    return next(
        (child for child in children[index + 1 :] if child.tag is not ET.Comment),
        None,
    )


def _collect_notes(node: ET.Element, type_name: str, notes: Notes) -> None:
    """Gather the comments below node, keyed by the component each describes."""
    children = list(node)
    for index, child in enumerate(children):
        if child.tag is not ET.Comment:
            child_type = (
                child.get("name", type_name) if child.tag in TYPE_TAGS else type_name
            )
            _collect_notes(child, child_type, notes)
            continue
        text = _squash(child.text)
        if not text or text in SECTION_HEADINGS:
            continue
        target = _comment_target(children, index)
        if target is not None and (key := _note_key(target, type_name)):
            notes[key] = f"{notes[key]} {text}" if key in notes else text


def _read_notes(path: Path) -> Notes:
    """Read an XSD's comments, which xmlschema discards."""
    # A schema file from this repository, not untrusted input.
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))  # noqa: S314
    root = ET.parse(path, parser).getroot()  # noqa: S314
    notes: Notes = {}
    _collect_notes(root, "", notes)
    return notes


def _code(text: str) -> str:
    """Format text as inline code."""
    return f"`{text}`"


def _type_ref(xsd_type: XsdType | None) -> str:
    """Show a built-in type as code and link a schema type to its section."""
    if xsd_type is None:
        return ""
    if xsd_type.target_namespace == XSD_NAMESPACE:
        return _code(xsd_type.prefixed_name or "")
    name = xsd_type.local_name or ""
    return f"[{name}](#{name.lower()})"


def _occurs(occurs: tuple[int, int | None]) -> str:
    """Format min and max occurrences like a UML multiplicity."""
    low, high = occurs
    high_text = "*" if high is None else str(high)
    return high_text if str(low) == high_text else f"{low}..{high_text}"


def _default(value: str | None) -> str:
    """Format a default value, which may be the empty string."""
    if value is None:
        return ""
    return _code(value) if value else _code('""')


def _table(header: Sequence[str], rows: Iterable[Sequence[str]]) -> list[str]:
    """Render a markdown table, leaving out columns with no values."""
    rows = list(rows)
    keep = [
        index
        for index in range(len(header))
        if index == 0 or any(row[index] for row in rows)
    ]
    lines = [
        "| " + " | ".join(header[index] for index in keep) + " |",
        "| " + " | ".join("---" for _ in keep) + " |",
    ]
    lines.extend(
        "| " + " | ".join(row[index].replace("|", r"\|") for index in keep) + " |"
        for row in rows
    )
    return [*lines, ""]


def _content_lines(xsd_type: XsdComplexType, name: str, notes: Notes) -> list[str]:
    """Describe a complex type's text content or child elements."""
    content = xsd_type.content
    if not isinstance(content, XsdGroup):
        return [f"Text of type {_type_ref(content)}.", ""]
    elements = list(content.iter_elements())
    if not elements:
        return []
    rows = (
        (
            _code(element.local_name or ""),
            _type_ref(element.type),
            _occurs(element.occurs),
            _default(element.default),
            notes.get(("element", name, element.local_name or ""), ""),
        )
        for element in elements
    )
    return [
        MODEL_INTROS[content.model],
        "",
        *_table(("Element", "Type", "Occurs", "Default", "Notes"), rows),
    ]


def _attribute_lines(xsd_type: XsdComplexType, name: str, notes: Notes) -> list[str]:
    """Describe a complex type's attributes."""
    rows = [
        (
            _code(attr_name),
            _type_ref(attribute.type),
            attribute.use or "",
            _default(attribute.default),
            notes.get(("attribute", name, attr_name), ""),
        )
        for attr_name, attribute in xsd_type.attributes.items()
        if isinstance(attr_name, str)
    ]
    if not rows:
        return []
    return [
        "Attributes:",
        "",
        *_table(("Attribute", "Type", "Use", "Default", "Notes"), rows),
    ]


def _assert_lines(xsd_type: XsdComplexType, name: str, notes: Notes) -> list[str]:
    """Describe a complex type's XSD 1.1 assertions."""
    lines = []
    for assertion in xsd_type.assertions:
        test = _squash(assertion.path)
        note = notes.get(("assert", name, test))
        lines.append(f"- {note} {_code(test)}" if note else f"- {_code(test)}")
    return ["Rules:", "", *lines, ""] if lines else []


def _complex_lines(xsd_type: XsdComplexType, name: str, notes: Notes) -> list[str]:
    """Describe a complex type."""
    return [
        *_content_lines(xsd_type, name, notes),
        *_attribute_lines(xsd_type, name, notes),
        *_assert_lines(xsd_type, name, notes),
    ]


def _restriction_lines(
    restriction: XsdAtomicRestriction, name: str, notes: Notes
) -> list[str]:
    """Describe a restriction's allowed values and facets."""
    lines = []
    if restriction.enumeration:
        rows = (
            (_code(str(value)), notes.get(("enumeration", name, str(value)), ""))
            for value in restriction.enumeration
        )
        lines += _table(("Value", "Notes"), rows)
    facets = []
    if restriction.patterns is not None:
        facets += [
            f"- Pattern: {_code(regex)}" for regex in restriction.patterns.regexps
        ]
    for facet_name, facet in restriction.facets.items():
        label = FACET_LABELS.get(facet_name or "")
        if label and isinstance(facet, XsdFacet):
            # The value as written, which xmlschema normalizes ("5.0" to 5).
            facets.append(f"- {label}: {_code(facet.elem.get('value', ''))}")
    return [*lines, *facets, ""] if facets else lines


def _lead(text: str, body: Sequence[str]) -> list[str]:
    """End a lead sentence with a colon when a table or list follows it."""
    return [f"{text}:" if body else f"{text}.", "", *body]


def _simple_lines(xsd_type: XsdType, name: str, notes: Notes) -> list[str]:
    """Describe a simple type."""
    if isinstance(xsd_type, XsdList):
        item = xsd_type.item_type
        body = (
            _restriction_lines(item, name, notes)
            if isinstance(item, XsdAtomicRestriction)
            else []
        )
        base = _type_ref(item.base_type or item)
        return _lead(f"A space-separated list of {base} values", body)
    if isinstance(xsd_type, XsdAtomicRestriction):
        body = _restriction_lines(xsd_type, name, notes)
        return _lead(f"Restricts {_type_ref(xsd_type.base_type)} to", body)
    return []


def _type_section(name: str, xsd_type: XsdType, notes: Notes) -> list[str]:
    """Render one named type's heading, notes and description."""
    lines = [f"### {name}", ""]
    if note := notes.get(("type", name, "")):
        lines += [note, ""]
    if isinstance(xsd_type, XsdComplexType):
        return lines + _complex_lines(xsd_type, name, notes)
    return lines + _simple_lines(xsd_type, name, notes)


def _title(path: Path) -> str:
    """Make a page title from the file name, as ComicInfo-v2.1-Draft.xsd."""
    return re.sub(r"-v(?=\d)", " ", path.stem).replace("-", " ")


def render(path: Path) -> str:
    """Render one XSD as a markdown page."""
    schema = xmlschema.XMLSchema11(path)
    notes = _read_notes(path)
    lines = [
        f"# {_title(path)}",
        "",
        f"Generated from [{path.name}]({SOURCE_URL}{path.name}).",
        "",
    ]
    for element in schema.elements.values():
        root = _code(element.local_name or "")
        lines += [f"The root element is {root}, of type {_type_ref(element.type)}.", ""]
    sections = (
        ("Complex Types", lambda t: isinstance(t, XsdComplexType)),
        ("Simple Types", lambda t: not isinstance(t, XsdComplexType)),
    )
    for heading, wanted in sections:
        types = [(name, t) for name, t in schema.types.items() if wanted(t)]
        if types:
            lines += [f"## {heading}", ""]
            for name, xsd_type in types:
                lines += _type_section(name, xsd_type, notes)
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    """Write a docs page for every XSD comicbox ships."""
    for path in sorted(SCHEMAS_DIR.glob("*.xsd")):
        (DEST / f"{path.name}.md").write_text(render(path))


if __name__ == "__main__":
    main()
