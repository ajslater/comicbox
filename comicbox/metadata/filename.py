"""
Parse comic book archive names using the simple 'parse' parser.

A more sophisticaed library like pyparsing or rebulk might be able to
build a faster, more powerful matching engine with fewer parsers with
optional fields. But this brute force method with the parse library is
effective, simple and easy to read and to contribute to.
"""

import re

from logging import getLogger
from pathlib import Path

from parse import compile, with_pattern

from comicbox.metadata.comic_base import ComicBaseMetadata


LOG = getLogger(__name__)


@with_pattern(r"#?(\d|½)+\.?\d*\w*")
def issue(text):
    """Issue number."""
    res = ComicBaseMetadata.parse_issue(text)
    return res


@with_pattern(r"v(?:ol)?\.? ?\d+")
def volume(text):
    """Volume number or year."""
    text = text.lstrip("vV")
    text = text.lstrip("oO")
    text = text.lstrip("lL")
    text = text.lstrip(".")
    text = text.lstrip(" ")
    return int(text)


@with_pattern(r"\(\d{4}\)")
def year(text):
    """Year."""
    return int(text[1:-1])


@with_pattern(r"\(?of \d+\)?")
def issue_count(text):
    """Issue count suffix."""
    text = text.split()[1]
    text = text.rstrip(")")
    return int(text)


@with_pattern(r"([^\.\s]*)$")
def ext(text):
    """Last File Extension."""
    return text


def compile_parsers(patterns):
    """Compile patterns into parsers without spewing debug logs."""
    from logging import getLogger

    log = getLogger("parse")
    old_level = log.level
    log.setLevel("INFO")
    parsers = tuple(
        [
            compile(
                pattern,
                {
                    "issue": issue,
                    "volume": volume,
                    "year": year,
                    "issue_count": issue_count,
                    "ext": ext,
                },
            )
            for pattern in patterns
        ]
    )
    log.setLevel(old_level)
    return parsers


class FilenameMetadata(ComicBaseMetadata):
    """Extract metadata from the filename."""

    ALL_FIELDS = frozenset(["series", "volume", "issue", "issue_count", "year", "ext"])
    FIELD_SCHEMA = {key: None for key in ALL_FIELDS}
    # The order of these patterns is very important as patterns farther down
    # match after patterns at the top.

    PATTERNS = (
        "{series} {volume:volume} {issue:issue} {title} {year:year} {remainder}"
        + ".{ext:ext}",
        "{series} {volume:volume} {title} {year:year} {remainder}.{ext:ext}",
        "{series} {issue:issue} {year:year} {remainder}.{ext:ext}",
        "{series} {issue:issue} {issue_count:issue_count} {year:year} "
        "{remainder}.{ext:ext}",
        "{series} {volume:volume} {title} {year:year} {remainder}.{ext:ext}",
        "{series} {volume:volume} {issue:issue} {title} {year:year} {remainder}"
        + ".{ext:ext}",
        "{series} {volume:volume} {year:year} {issue:issue} {title} {remainder}"
        + ".{ext:ext}",
        "{series} {volume:volume}{garbage}{year:year} {remainder}.{ext:ext}",
        "{series} {volume:volume} {title} {year:year} {remainder}.{ext:ext}",
        "{series} {volume:volume} {year:year} {remainder}.{ext:ext}",
        "{series} {volume:volume} {year:year} {issue:issue} {remainder}.{ext:ext}",
        "{series} {volume:volume} {issue:issue} {title} {year:year} {remainder}"
        + ".{ext:ext}"
        "{series} {volume:volume} {issue:issue}.{ext:ext}"
        "{series} {volume:volume} {title} {year:year} {remainder}.{ext:ext}"
        "{series} {issue:issue} {issue_count:issue_count} {year:year} "
        "{remainder}.{ext:ext}",
        "{series} {issue:issue} {issue_count:issue_count} {remainder}.{ext:ext}",
        "{series} {issue:issue} {year:year}.{ext:ext}",
        "{series} {issue:issue} {year:year} {remainder}.{ext:ext}",
        "{series} {year:year} {issue:issue} {remainder}.{ext:ext}",
        "{series} {year:year} {remainder}.{ext:ext}",
        "{series} {volume:volume} {issue:issue}.{ext:ext}",
        "{series} {volume:volume} {issue:issue} {remainder}.{ext:ext}",
        "{series} {issue:issue} {remainder}.{ext:ext}",
        "{series} {issue:issue}.{ext:ext}",
        "{series}.{ext:ext}",
        "{issue:issue} {series}.{ext:ext}",
        "{issue:issue} {series} {remainder}.{ext:ext}",
    )

    PATTERN_MAX_MATCHES = tuple([pattern.count("}") for pattern in PATTERNS])
    PARSERS = compile_parsers(PATTERNS)
    SPACE_ALT_CHARS_RE = re.compile(r"_")
    DIVIDERS = re.compile(r" -|: ")
    PLUS_RE = re.compile(r"\++")
    MULTI_SPACE_RE = re.compile(r"\s{2,}")
    FILENAME_TAGS = (
        ("series", "{}"),
        ("volume", "v{}"),
        ("issue", ""),
        ("issue_count", "(of {:03})"),
        ("year", "({})"),
        ("title", "{}"),
    )

    @staticmethod
    def try_parser(parser, fn):
        """Try one parser and return the results as a dict."""
        res = parser.parse(fn)
        if res:
            return res.named
        return {}

    @staticmethod
    def issue_formatter(issue):
        """Formatter to zero pad issues."""
        i = 0
        for c in issue:
            if not c.isdigit():
                break
            i += 1
        pad = 3 + len(issue) - i
        return "#{:0" + str(pad) + "}"

    def clean_fn(self, filename):
        """Clean out distracting characters from the filename."""
        fn = self.SPACE_ALT_CHARS_RE.sub(" ", filename)
        fn = self.DIVIDERS.sub(" ", fn)
        fn = self.PLUS_RE.sub(" ", fn)
        fn = self.MULTI_SPACE_RE.sub(" ", fn)
        return fn

    def from_string(self, path):
        """Try all parsers against the filename and return the best result."""
        self._path = Path(path)
        fn = self.clean_fn(self._path.name)
        best_res = {}
        pattern_num = 0
        for parser in self.PARSERS:
            try:
                res = self.try_parser(parser, fn)
                if len(res) > len(best_res):
                    best_res = res
                    if len(best_res) == self.PATTERN_MAX_MATCHES[pattern_num]:
                        # if we match everything in the pattern end early.
                        LOG.debug(f"{pattern_num} {self.PATTERNS[pattern_num]}")
                        break
                pattern_num += 1
            except Exception as exc:
                LOG.debug(f"{self.path} {exc}")
        self.metadata.update(best_res)

    def from_file(self, path):
        """Oddly this ends up being identical."""
        return self.from_string(path)

    def to_string(self):
        """Get our preferred basename from a metadata dict."""
        tokens = []
        for tag, fmt in self.FILENAME_TAGS:
            val = self.metadata.get(tag)
            if val:
                if tag == "issue":
                    fmt = self.issue_formatter(val)
                token = fmt.format(val)
                tokens.append(token)
        name = " ".join(tokens)
        return name

    def to_file(self, path):
        """Rename this file according to our favorite naming scheme."""
        name = self.to_string()
        new_path = path.parent / Path(name + path.suffix)
        old_path = path
        path.rename(new_path)
        LOG.info(f"Renamed:\n{old_path} ==> {self._path}")
        return new_path
