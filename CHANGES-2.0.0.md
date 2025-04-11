# Changes 2.0.0

## Config & CLI

### New Options

#### metadata_format

Hint to the metadata parser what format API metadata will be parsed as. Config
Only.

#### stamp

Normally comicbox will only update the notes (if enabled), tagger, and
updated_at tags when performing a write or export action. This adds the stamps
anyway.

#### theme

[Pygments theme](https://pygments.org/styles/) to use for syntax highlighting. .
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

[MetadataSources](comicbox/sources.py) and
[MetadataFormats](comicbox/formats.py) have been separated and are now different
related Enums.

### box.extract_covers()

Was named box.extract_covers_as()

### get_pages() pdf to pixmap methods

The boolean argument to return pdf pages as pixmaps when getting pages has gone
away and was replaced by new methods:

- box.get_cover_page_pdf_to_pixmap
- box.get_page_by_filename_pdf_to_pixmap()
- box.get_page_by_index_pdf_to_pixmap()
- box.get_pages_pdf_to_pixmap()

## Comicbox Schema

The largest changes are to the internal Comicbox metadata schema that comicbox
returns with box.get_metadata(). It is more hierarchical and what used to be
lists are now often dicts with potentially empty values that when Metron data is
parsed could have identifiers in them.

[The Comicbox 2.0 JSON Schema](https://github.com/ajslater/comicbox/tree/main/comicbox/schemas/v2.0/)
is available.
