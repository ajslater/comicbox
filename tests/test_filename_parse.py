"""Tests for filename parsing."""
from copy import deepcopy

import pytest

from comicbox.metadata.filename import FilenameMetadata
from tests.test_filenames import FNS


# from comicbox.old_filenameparser import FileNameParser
# from test_filenames import INT_FIELDS


# def fnp_to_dict(fnp):
#    res = {}
#    for key in ALL_FIELDS:
#        val = getattr(fnp, key, None)
#        if val == "":
#            val = None
#        if key in INT_FIELDS and val is not None:
#            val = int(val)
#        res[key] = val
#    return res


@pytest.mark.parametrize("item", FNS.items())
def test_parse_filename(item):  # , fnp, fnp_name):
    fn, defined_fields = item
    #    if fnp and fnp_name:
    #        fnp.parseFilename(fn)
    #       res = fnp_to_dict(fnp)
    #    elif fnp_name == "parse":
    parser = FilenameMetadata()
    parser.parse_filename(fn)
    res = parser.metadata
    #    else:
    #        print("No file name parser defined")
    #        exit(1)
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


# def common_tester(fnp=None, fnp_name=None):
#    for fn, defined_fields in FNS.items():
#        common_test(fn, defined_fields, fnp, fnp_name)


# def main():
#    common_tester(FileNameParser(), "old_fnp")
#    common_tester(None, "parse")


# if __name__ == "__main__":
#    main()
