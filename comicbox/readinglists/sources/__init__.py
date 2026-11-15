"""
Where reading lists are fetched from: URLs, Metron and the DieselTech catalog.

Network libraries are imported inside functions, so importing this package
stays cheap; only a fetch pays for them.
"""

from collections.abc import Mapping
from typing import Any

from comicbox.empty import is_empty
from comicbox.readinglists.schema import SOURCE_KIND_KEY, SOURCES_KEY, SourceKind


def attach_source(
    reading_list: Mapping[str, Any], source: Mapping[str, Any]
) -> dict[str, Any]:
    """
    Record where a fetched list came from.

    A file read gives its list a source of kind ``file``; a fetched one came
    from ``source`` instead, so that one takes its place, keeping what it
    knew that ``source`` does not, such as a CBL's curator. A list with no
    file source gets ``source`` first.
    """
    fetched = {key: value for key, value in source.items() if not is_empty(value)}
    sources = [dict(item) for item in reading_list.get(SOURCES_KEY) or ()]
    for index, item in enumerate(sources):
        if item.get(SOURCE_KIND_KEY) == SourceKind.FILE.value:
            del item[SOURCE_KIND_KEY]
            sources[index] = {**item, **fetched}
            break
    else:
        sources.insert(0, fetched)
    return {**reading_list, SOURCES_KEY: sources}
