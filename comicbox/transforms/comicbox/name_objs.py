"""Transform string lists to comicbox name objects and back."""

from collections.abc import Mapping

from comicbox.transforms.transform_map import KeyTransforms


def string_list_to_name_obj(_source_data: Mapping, names):
    """Transform one sequence of strings to comicbox name objects."""
    return {name: {} for name in names if name}


def name_obj_to_string_list(_source_data: Mapping, obj):
    """Transform one comicbox name object to a string list."""
    return [name for name in obj if name]


def name_obj_to_string_list_key_transforms(key_map):
    """Create a name obj to string list key transform spec for a key map."""
    return KeyTransforms(
        key_map=key_map,
        to_cb=string_list_to_name_obj,
        from_cb=name_obj_to_string_list,
    )
