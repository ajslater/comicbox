"""
Computed metadata methods, and the ordered pipeline that runs them.

Each computed action reads the merged metadata snapshot and returns a delta.
The delta is merged back into that snapshot before the next action runs, so
order is part of the contract rather than an implementation detail:
``identifiers from urls`` must see the urls ``urls from notes`` collected,
``urls`` must see every identifier the earlier actions found, and
``Tagger Stamp`` must run after both because it bakes the finished
identifiers into the notes text it writes.

That order used to be an accident of the mixin MRO. Each of the nine modules
in this package spliced its own actions into the inherited ``COMPUTED_ACTIONS``
mapping with a dict splat, so reading the pipeline meant walking the
inheritance chain backwards - and ``pages`` spliced its two actions in *front*
of the inherited ones while the other eight appended, which is the only reason
the page actions run first. ``COMPUTED_ACTIONS`` below is that same order,
written out once, in one place.

Actions are registered by method *name*, not by the function object lifted out
of a class body. The splat captured unbound functions, so a subclass overriding
a computed method was silently never called; ``getattr(self, name)`` dispatches
through the instance like every other method call.
"""

from collections.abc import Hashable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from types import MappingProxyType
from typing import Any

from comicfn2dict.parse import comicfn2dict
from comicfn2dict.regex import ORIGINAL_FORMAT_RE
from glom import glom
from loguru import logger

from comicbox.box.computed.stories_title import ComicboxComputedStoriesTitle
from comicbox.empty import is_empty
from comicbox.formats.base.fields.enum_fields import OriginalFormatField
from comicbox.formats.base.transforms.xml_reprints import FILENAME_TO_REPRINT_SPECS
from comicbox.formats.comicbox.schema import (
    NAME_KEY,
    ORIGINAL_FORMAT_KEY,
    REPRINTS_KEY,
    SCAN_INFO_KEY,
    ComicboxSchemaMixin,
)
from comicbox.merge import AdditiveMerger, Merger, ReplaceMerger


def _prune_empty(value: Any) -> Any:
    """Drop the empty slots the filename grammar leaves behind."""
    if isinstance(value, Mapping):
        return {
            key: pruned
            for key, sub_value in value.items()
            if not is_empty(pruned := _prune_empty(sub_value))
        }
    return value


# One spec, built once. dict() on the specs ran per reprint name.
_FILENAME_TO_REPRINT_SPECS = dict(FILENAME_TO_REPRINT_SPECS)


@lru_cache(maxsize=1024)
def _parse_reprint_name(name: str) -> Mapping[str, Any]:
    """
    Read a reprint's name with the filename grammar, once per distinct name.

    Both the grammar and the glom spec are pure functions of the name, and
    names repeat: a reprint-heavy book is mostly the same few editions said
    twice, which is what the consolidation pass exists for.

    The result is shared between callers and must be treated as read only.
    Everything that reaches a reprint from here goes through
    ``_prune_empty``, which builds a fresh container at every mapping level.
    """
    return glom(comicfn2dict(name), _FILENAME_TO_REPRINT_SPECS)


def _comparable(value: Any) -> Hashable:
    """
    One reprint value in the form two reprints can be compared by.

    Sources disagree about representation without disagreeing about
    content: a volume number read out of a reprint's name is the string
    ``"2"`` where the same number loaded through the schema is the int
    ``2``, and capitalization is a source's habit rather than a fact about
    the edition.
    """
    if isinstance(value, Mapping):
        return frozenset(
            (key, _comparable(sub_value)) for key, sub_value in value.items()
        )
    if isinstance(value, Sequence | AbstractSet) and not isinstance(value, str | bytes):
        # Order is the serializer's choice, so compare as a multiset.
        return tuple(sorted((_comparable(item) for item in value), key=repr))
    return str(value).casefold()


def _reprint_fields(reprint: Mapping, prefix: str = "") -> dict[str, Hashable]:
    """Flatten a reprint to comparable leaf values, keyed by dotted path."""
    fields: dict[str, Hashable] = {}
    for key, value in reprint.items():
        path = f"{prefix}{key}"
        if isinstance(value, Mapping):
            fields.update(_reprint_fields(value, f"{path}."))
        else:
            fields[path] = _comparable(value)
    return fields


def _reprints_agree(
    left: Mapping[str, Hashable], right: Mapping[str, Hashable]
) -> bool:
    """
    Whether two flattened reprints describe one edition rather than two.

    They do when neither contradicts the other on a field they both carry.
    Sharing no field at all is not agreement — that is two editions, not one
    said twice — unless one of them makes no claim to contradict.
    """
    if not left or not right:
        return True
    shared = left.keys() & right.keys()
    return bool(shared) and all(left[path] == right[path] for path in shared)


@dataclass
class ComputedData:
    """Computed metadata."""

    label: str
    metadata: Mapping | None
    merger: type[Merger] | None = AdditiveMerger


@dataclass(frozen=True)
class ComputedAction:
    """One step of the computed pipeline."""

    label: str
    method_name: str
    merger: type[Merger] | None = AdditiveMerger


class ComicboxComputed(ComicboxComputedStoriesTitle):
    """Computed metadata methods."""

    def _get_computed_from_scan_info(
        self, sub_data: dict[str, Any], **_kwargs: Any
    ) -> dict[str, Any] | None:
        """Parse scan_info for original format info."""
        if ORIGINAL_FORMAT_KEY in self._config.general.delete_keys or not sub_data:
            return None
        scan_info = sub_data.get(SCAN_INFO_KEY)
        if not scan_info or sub_data.get(ORIGINAL_FORMAT_KEY):
            return None

        match = ORIGINAL_FORMAT_RE.search(scan_info)
        if not match:
            return None
        try:
            # Normalize through the field so the computed value matches the
            # canonical enum form every other original_format path uses.
            original_format = OriginalFormatField().deserialize(
                match.group(ORIGINAL_FORMAT_KEY)
            )
        except Exception as exc:
            # Garbage scan_info must not abort the whole computed pass —
            # warn-and-skip matches the other computed actions.
            logger.warning(f"Could not normalize original_format from scan_info: {exc}")
            return None
        if not original_format:
            return None
        return {ORIGINAL_FORMAT_KEY: original_format}

    def _get_computed_from_reprint_names(
        self, sub_data: dict[str, Any]
    ) -> dict[str, list] | None:
        """
        Read what a reprint's name says about its series, volume and issue.

        The name is free text the source wrote, so this is enrichment for
        readers, never the authority: it only fills fields the reprint left
        empty, and the name itself is what gets written back.
        """
        if REPRINTS_KEY in self._config.general.delete_keys or not sub_data:
            return None
        old_reprints = sub_data.get(REPRINTS_KEY)
        if not old_reprints:
            return None
        new_reprints = []
        enriched = False
        for old_reprint in old_reprints:
            new_reprint = dict(old_reprint)
            name = new_reprint.get(NAME_KEY)
            if name:
                parsed = _parse_reprint_name(str(name))
                for key, value in parsed.items():
                    # The filename grammar yields a slot for every field it
                    # knows, empty when the name didn't say.
                    pruned = _prune_empty(value)
                    if key not in new_reprint and not is_empty(pruned):
                        new_reprint[key] = pruned
                        enriched = True
            new_reprints.append(new_reprint)
        if not enriched:
            return None
        return {REPRINTS_KEY: new_reprints}

    def _get_computed_from_reprints(
        self, sub_data: dict[str, Any]
    ) -> dict[str, list] | None:
        """Consolidate reprints."""
        if REPRINTS_KEY in self._config.general.delete_keys or not sub_data:
            return None
        old_reprints = sub_data.get(REPRINTS_KEY)
        if not old_reprints:
            return None
        # Compare flattened, normalized fields rather than diffing every pair
        # of nested reprints. The DeepDiff this replaces was ~93% of the whole
        # computed pass on a reprint-heavy book, and its ignore_order pairing
        # decided agreement by a similarity threshold, so whether two reprints
        # consolidated depended on how many fields they *didn't* share.
        fields = [_reprint_fields(reprint) for reprint in old_reprints]
        new_reprints = []
        merged_indexes = set()
        for index, old_reprint in enumerate(old_reprints):
            if index in merged_indexes:
                continue
            # A leader absorbs what agrees with it, so its fields grow as the
            # scan runs and later candidates are compared against everything
            # it has taken on. The scan starts past the leader itself: it used
            # to begin at the leader, merging a dict into itself, which
            # mergedeep skips outright.
            for sub_index in range(index + 1, len(old_reprints)):
                if _reprints_agree(fields[index], fields[sub_index]):
                    AdditiveMerger.merge(old_reprint, old_reprints[sub_index])
                    fields[index] = _reprint_fields(old_reprint)
                    merged_indexes.add(sub_index)
            new_reprints.append(old_reprint)

        if len(old_reprints) != len(new_reprints):
            return {REPRINTS_KEY: new_reprints}
        return None

    def _all_delete_keys(self) -> frozenset[str]:
        """
        Every key path the delete pass must remove.

        The config's own delete_keys, plus the ones the computed pass earned
        as it ran: a date part that cannot be part of any real date names
        itself here rather than surviving into the metadata.
        """
        return frozenset(self._config.general.delete_keys | self._extra_delete_keys)

    def _get_delete_keys(self, _sub_data: Mapping) -> tuple | None:
        delete_keys = self._all_delete_keys()
        if not delete_keys:
            return None
        return tuple(sorted(delete_keys))

    # Order is the contract. See the module docstring.
    COMPUTED_ACTIONS: tuple[ComputedAction, ...] = (
        # What the archive itself says, independent of every other action.
        ComputedAction(
            "Page Count", "_get_computed_page_count_metadata", ReplaceMerger
        ),
        ComputedAction("Pages", "_get_computed_pages_metadata", ReplaceMerger),
        # Identifiers, weakest source last: a url names an id more plainly
        # than notes prose, and notes prose more plainly than a tag.
        ComputedAction("urls from notes", "_get_computed_urls_from_notes"),
        ComputedAction("identifiers from urls", "_get_computed_identifiers_from_urls"),
        ComputedAction("from notes", "get_computed_from_notes"),
        ComputedAction("from tags", "_get_computed_from_tags"),
        ComputedAction("normalize identifier keys", "_normalize_all_identifier_keys"),
        # Synthesize the urls the identifiers imply, then stamp the finished
        # identifiers into notes.
        ComputedAction("urls", "_get_computed_urls", ReplaceMerger),
        ComputedAction("Tagger Stamp", "_get_tagger_stamp", ReplaceMerger),
        # Field derivations. Each reads one branch of the tree and writes
        # another, so they only depend on the merged metadata.
        ComputedAction("from manga_volume", "_get_computed_from_manga_volume"),
        ComputedAction("from issue", "_get_computed_from_issue"),
        ComputedAction("from issue.number & issue.suffix", "_get_computed_issue"),
        ComputedAction(
            "from alternative_issue", "_get_computed_from_alternative_issue"
        ),
        ComputedAction(
            "from alternative_issue.number & alternative_issue.suffix",
            "_get_computed_alternative_issue",
        ),
        ComputedAction("from date", "_get_computed_from_date"),
        # title & stories feed each other; whichever the book has fills the
        # other, and the second action sees the first one's result.
        ComputedAction("from title", "_get_computed_from_title"),
        ComputedAction("from stories", "_get_computed_from_stories"),
        ComputedAction(
            "from reprint names", "_get_computed_from_reprint_names", ReplaceMerger
        ),
        ComputedAction("from reprints", "_get_computed_from_reprints", ReplaceMerger),
        ComputedAction("from scan_info", "_get_computed_from_scan_info"),
        # Reports the delete pass's key paths for --print; deletion itself
        # happens in ComicboxMetadata, after every action has run.
        ComputedAction("Delete Keys", "_get_delete_keys", None),
    )

    def _set_computed_metadata(self) -> None:
        computed_list = []
        # Deep copy: actions receive sub_data and some (reprints) merge
        # entries in place; without the copy they'd silently mutate the
        # cached merged metadata they're supposed to derive from.
        computed_merged_md = deepcopy(dict(self.get_merged_metadata()))
        sub_data: dict[str, Any] = computed_merged_md.setdefault(
            ComicboxSchemaMixin.ROOT_TAG, {}
        )
        # Actions add to this as they run; a recompute starts over.
        self._extra_delete_keys = set()

        # Compute each
        for action in self.COMPUTED_ACTIONS:
            method = getattr(self, action.method_name)
            sub_md = method(sub_data)
            if not sub_md:
                continue

            if action.merger:
                # Actions derive from each other: normalized keys build urls,
                # and both are stamped into notes. Merge the delta into the
                # snapshot so later actions see it. That accumulated snapshot
                # *is* the computed metadata — ComicboxMetadata reads it back
                # instead of replaying every delta onto a second copy.
                #
                # The delta is merged as-is. It used to be deep copied first,
                # to keep the stored delta from aliasing a snapshot a later
                # action may change, but mergedeep never lends the source's
                # objects to the destination: every branch of it either
                # recurses into the destination's own mapping or assigns a
                # deepcopy. Copying here only did that same work twice.
                action.merger.merge(sub_data, sub_md)

            md = {ComicboxSchemaMixin.ROOT_TAG: sub_md}
            computed_data = ComputedData(action.label, md, action.merger)
            computed_list.append(computed_data)

        # Set values
        self._computed = tuple(computed_list)
        self._computed_merged_metadata = MappingProxyType(computed_merged_md)
        self._computed_dict_formats = self._dict_formats

    def _ensure_computed_metadata(self) -> None:
        """Recompute when the dict-format context changed."""
        # pages/page_count computation consults _dict_formats, so a result
        # memoized under one to_dict() format must not leak into calls under
        # another.
        if (
            not self._computed_merged_metadata
            or self._computed_dict_formats != self._dict_formats
        ):
            self._set_computed_metadata()

    def get_computed_metadata(self) -> tuple:
        """Get the computed metadata deltas, labelled, for printing."""
        self._ensure_computed_metadata()
        return self._computed

    def get_computed_merged_metadata(self) -> MappingProxyType:
        """Get the merged metadata with every computed delta already applied."""
        self._ensure_computed_metadata()
        return self._computed_merged_metadata
