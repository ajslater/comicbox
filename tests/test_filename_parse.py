"""Tests for filename parsing."""
from copy import deepcopy

import pytest

from comicbox.metadata.filename import FilenameMetadata
from tests.test_filenames import FNS


@pytest.mark.parametrize("item", FNS.items())
def test_parse_filename(item):
    fn, defined_fields = item
    parser = FilenameMetadata(path=fn)
    res = parser.metadata
    matched_fields = set()
    unmatched_fields = []
    fields = deepcopy(FilenameMetadata.FIELD_SCHEMA)
    fields.update(defined_fields)
    for key, val in fields.items():
        if key == "remainder" or key == "ext":
            matched_fields.add(key)
            continue
        res_val = res.get(key)
        if res_val == val:
            matched_fields.add(key)
        else:
            unmatched_fields.append(f"{key}: {type(res_val)}-'{res_val}' != '{val}'")
    print(fn, ", ".join(unmatched_fields))
    assert FilenameMetadata.ALL_FIELDS - matched_fields == set()
