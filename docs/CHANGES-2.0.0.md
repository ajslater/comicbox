# 🛠️ Changes 2.0.0

This is not an exhaustive list of changes, but more of a reference sheet to get
you started if you have a workflow or library that depends on comicbox.

## Config & CLI

### New Options

#### compute_pages

False by default. Compute the complicated ComicInfo like Pages structure by
investigating the archive table of contents.

#### compute_page_count

True by default. Compute the page_count by investigating the archive table of
contents.

#### metadata_format

Hint to the metadata parser what format API metadata will be parsed as. Config
Only.

#### stamp

Normally comicbox will only update the notes (if enabled), tagger, and
updated_at tags when performing a write or export action. This adds the stamps
anyway.

#### theme

[Pygments theme](https://pygments.org/styles/) to use for syntax highlighting.
'none' will stop highlighting.

### Changed Actions

### covers

Was named `cover`.

#### delete-all-tags

Was named `delete`.

## New Formats

### MetronInfo

The [MetronInfo](https://metron-project.github.io/docs/category/metroninfo)
comic metadata format is now fully supported.

## API

### Metadata Formats and Metadata Sources

[MetadataSources](https://github.com/ajslater/comicbox/tree/main/comicbox/sources.py)
and
[MetadataFormats](https://github.com/ajslater/comicbox/tree/main/comicbox/formats.py)
are separated and are now different related Enums.

### Method name changes

- Comicbox.extract_covers_as() => Comicbox.extract_covers()
- Comicbox.get_cover_image() => Comicbox.get_cover_page()
- Comicbox.write() => Comicbox.dump()
- Comicbox.box.get_metadata() => Comicbox.box.get_internal_metadata()
    - Most applications should use box.to_dict()
- Comicbox.box.set_metadata() => Comicbox.box.set_internal_metadata()

## Pre Config

Configs submitted to Comicbox(config=) are processed and the config logic is
substantial. If you submit a pre-processed AttrDict config to Comicbox(config=)
it will not reprocess the config possibly saving some time. e.g.

```python
from comicbox.box import Comicbox
from comicbox.config import get_config

CONFIG = get_config({"print": "snp"})

for path in paths:
  with Comicbox(path, config=CONFIG) as cb:
    cb.print()
```

## Comicbox Schema

The largest changes are to the internal Comicbox metadata schema that comicbox
returns with box.get_metadata(). It's more hierarchical and what used to be
lists are now often dicts with potentially empty values that when Metron data is
parsed could have identifiers in them.

[The Comicbox 2.0 JSON Schema](https://github.com/ajslater/comicbox/tree/main/comicbox/schemas/v2.0/)
is available.
