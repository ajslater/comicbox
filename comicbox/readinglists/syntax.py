"""Describe a document that does not parse: what is wrong, and where."""

from xml.parsers.expat import ExpatError, ParserCreate

import simplejson
from ruamel.yaml import YAML
from ruamel.yaml.error import MarkedYAMLError, YAMLError

_JSON_OPENERS = ("{", "[")


def describe_syntax_error(exc: Exception) -> str:
    """Describe a parse error in one line, with its position."""
    if isinstance(exc, simplejson.JSONDecodeError):
        return f"Not valid JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}."
    if isinstance(exc, ExpatError):
        return f"Not valid XML: {exc}."
    if isinstance(exc, MarkedYAMLError) and (mark := exc.problem_mark) is not None:
        problem = exc.problem or exc.context or "a syntax error"
        return f"Not valid YAML: {problem} at line {mark.line + 1}, column {mark.column + 1}."
    return " ".join(str(exc).split())


def _xml_error(text: str) -> str | None:
    try:
        ParserCreate().Parse(text, True)  # noqa: FBT003
    except ExpatError as exc:
        return describe_syntax_error(exc)
    return None


def syntax_error(text: str) -> str | None:
    """
    Describe what keeps a document from parsing, or None when it parses.

    XML and JSON by their first character, anything else as YAML. Text that
    opens like JSON is held to JSON, even where it is valid YAML.
    """
    stripped = text.lstrip()
    if stripped.startswith("<"):
        return _xml_error(text)
    if stripped.startswith(_JSON_OPENERS):
        try:
            simplejson.loads(text)
        except ValueError as exc:
            return describe_syntax_error(exc)
        return None
    try:
        YAML(typ="safe", pure=True).load(text)
    except YAMLError as exc:
        return describe_syntax_error(exc)
    return None
