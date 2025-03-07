"""Dictionary functions."""

from collections.abc import Mapping


def case_insensitive_dict(d: dict) -> dict:
    """Make a dict with string keys case insensitive."""
    cid = {k.lower(): (k, v) for k, v in d.items()}
    return {v[0]: v[1] for v in cid.values()}


def deep_update(
    base_dict: dict | None,
    update_dict: Mapping,
    sort=False,  # noqa: FBT002
    case_insensitive=False,  # noqa: FBT002
) -> dict:
    """Deep Dict Update."""
    if base_dict is None:
        base_dict = {}
    for key, value in update_dict.items():
        if isinstance(value, dict):
            updated_dict = deep_update(
                base_dict.get(key, value.__class__()),
                value,
                sort=sort,
                case_insensitive=case_insensitive,
            )
            if case_insensitive:
                updated_dict = case_insensitive_dict(updated_dict)
            if sort:
                updated_dict = dict(sorted(updated_dict.items()))
            base_dict[key] = updated_dict
        else:
            base_dict[key] = value
    return base_dict
