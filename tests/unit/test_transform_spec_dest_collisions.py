"""
Two mappings may not claim the same destination keypath.

`_create_specs` plants every destination with glom's ``assign``, which resolved
a collision silently: the later mapping won the value but kept the earlier
one's insertion slot, so one of the two declarations simply stopped existing.
Nesting was worse. Claiming ``a`` after ``a.b`` replaced the whole subtree, and
claiming ``a.b`` after ``a`` set the nested spec as an *attribute* of the
enclosing ``Coalesce`` object, where nothing ever read it. Across 82 metaspecs
no one can see that keyspace, so the compiler has to.
"""

from __future__ import annotations

import pytest
from glom import glom

from comicbox.formats.base.transforms.spec import MetaSpec, create_specs_to_comicbox


def _compile(*metaspecs: MetaSpec, root: str = ""):
    return create_specs_to_comicbox(*metaspecs, comicbox_root_keypath=root)


def test_exact_duplicate_dest_raises() -> None:
    with pytest.raises(RuntimeError, match="is already claimed by"):
        _compile(
            MetaSpec(key_map={"dest": "one"}),
            MetaSpec(key_map={"dest": "two"}),
        )


def test_leaf_then_nested_dest_raises() -> None:
    """`a` first: the nested spec would be setattr'd onto it and vanish."""
    with pytest.raises(RuntimeError, match="nests inside"):
        _compile(
            MetaSpec(key_map={"a": "one"}),
            MetaSpec(key_map={"a.b": "two"}),
        )


def test_nested_then_leaf_dest_raises() -> None:
    """`a.b` first: assigning `a` would replace the whole subtree."""
    with pytest.raises(RuntimeError, match="encloses"):
        _compile(
            MetaSpec(key_map={"a.b": "one"}),
            MetaSpec(key_map={"a": "two"}),
        )


def test_duplicate_within_one_key_map_raises() -> None:
    """A key map can't hold the same key twice, but it can nest into itself."""
    with pytest.raises(RuntimeError, match="nests inside"):
        _compile(MetaSpec(key_map={"a": "one", "a.b": "two"}))


def test_sibling_nested_dests_compile_and_run() -> None:
    """Siblings share a branch without claiming it. Both must survive."""
    specs = _compile(
        MetaSpec(key_map={"series.name": "name"}),
        MetaSpec(key_map={"series.volume": "volume"}),
    )
    assert glom({"name": "Bat", "volume": 2}, dict(specs)) == {
        "series": {"name": "Bat", "volume": 2}
    }


def test_same_dest_in_separate_compiles_is_fine() -> None:
    """Every compile owns its own keyspace. SPECS_TO and SPECS_FROM are two."""
    assert _compile(MetaSpec(key_map={"dest": "one"}))
    assert _compile(MetaSpec(key_map={"dest": "two"}))


def test_collision_across_root_inheritance_is_caught() -> None:
    """A rooted dest and a spelled out one address the same key."""
    with pytest.raises(RuntimeError, match="is already claimed by"):
        _compile(
            MetaSpec(key_map={"dest": "one"}),
            MetaSpec(key_map={"comicbox.dest": "two"}, inherit_root_keypath=False),
            root="comicbox",
        )


def test_error_names_both_claimants_and_the_compile() -> None:
    """The keyspace is invisible, so the error has to say where to look."""
    with pytest.raises(RuntimeError) as exc_info:
        create_specs_to_comicbox(
            MetaSpec(key_map={"other": "zero"}),
            MetaSpec(key_map={"dest": "one"}),
            MetaSpec(key_map={"dest": "two"}),
            format_root_keypath="MetronInfo",
            comicbox_root_keypath="comicbox",
        )
    reason = str(exc_info.value)
    assert "MetronInfo -> comicbox" in reason
    assert "metaspec[1]" in reason
    assert "metaspec[2]" in reason
    assert "comicbox.dest" in reason
