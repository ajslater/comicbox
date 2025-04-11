# Changes 1.0.0

This is not an exhaustive list of changes, but more of a reference sheet to get
you started if you have a workflow or library that depends on comicbox.

## CLI

Nearly completely changed.

`path` is no longer a required parameter for many actions.

`-m --metadata` is now in YAML "flow style", a one line yaml format. The CLI
`-m` option may accept _any_ tag from any supported format in YAML flow style.
Collisions are synthesized similarly to how metadata is read from the archive.

## Configuration

read*\*, write*\_, export\_\_ and print\_\* boolean flags are now read, write,
export and print options that take lists of strings to configure the behavior.

### read & write

The old system of `read_comicbookinfo` and `write_comicbookinfo` booleans has
been replaced by the `read`, `write` and `export` config attributes which are
all lists of config strings that represent formats. This is documented in the
cli.

```yaml
Format keys for --ignore-read, --write, and --export:
  Filename: fn, filename (read only)
  PDF: pdf
  CoMet: comet
  ComicBookInfo: cbi, comicbooklover, comicbookinfo, cbl
  ComicInfo: cix, comicrack, comicinfo, cr, ci, comicinfoxml
  ComicTagger: comictagger, ct
  Comicbox XML: xml (read only)
  Comicbox YAML: yaml
  Comicbox JSON: json, comicbox, cb
  Comicbox CLI: cli
```

## New Formats

### Comictagger

A JSON format that represents the API output of the comictagger tool.

### Comicbox

The internal comicbox format can be represented in JSON and YAML formats. You
may notice a read only XML comicbox format as well, but that is not intended to
be written.

### CLI Format

The CLI format is same as the comicbox YAML format but in "flow style" a single
line YAML format. The CLI however processes tags from any supported format, so
you don't have to remember Comicbox's internal format if you don't want to.

### PDF

comicbox has learned how to read and write pdf metadatada and export pdf covers
and pages.

## Features

Comicbox is now much better about ensuring string fields are stripped of
surrounding whitespace.

Comicbox tries to extract the identifiers from the notes field if Comictagger
put it there.

Comicbox continues _not_ to validate input but rather try to coerce the input
into a sensible value or skip the field with warning, rather than throwing an
exception.

## API

| Old                                 | New                       |
| ----------------------------------- | ------------------------- |
| comicbox.comic_archive.ComicArchive | comicbox.box.Comicbox     |
| ComicArchive.get_num_pages()        | Comicbox.get_page_count() |

Can perform many operations with a null `path`

`page_count` is generated from looking at the archive contents and applied over
metadata values read or submitted.

`pages` is generated from looking at the archive contents and is merged with
metadata values read or submitted.

### Comicbox Schema

#### Field Names

| Old             | New          | Type         |
| --------------- | ------------ | ------------ |
| black_and_white | monochrome   | bool         |
| credits         | contributors | list -> dict |
| description     | summary      | string       |
| comments        | summary      | string       |
|                 | protagonist  | string       |
|                 | identifiers  | dict         |
|                 | tagger       | string       |
|                 | updated_at   | datetime     |

#### Notes

tagger, updated_at and identifiers are parsed and unparsed from and to notes
when possible.
