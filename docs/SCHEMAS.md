# 📋 Schemas

Comicbox supports reading and writing several comic book metadata schemas.

## Filename Schema

Comicbox includes a pretty good comic archive filename parser. It can extract a
number of common fields from comic archive filenames.

The filename parser is available as a separate library:
[comicfn2dict](https://github.com/ajslater/comicfn2dict)

| Location      | Name                  |
| ------------- | --------------------- |
| Archive       | The archive filename  |
| Import/Export | comicbox-filename.txt |

## ComicInfo Schema v2.1 Draft (Comic Rack)

This schema used by the defunct Comic Rack reader is the de facto standard for
comic book metadata on the internet. The
[Anansi Project](https://anansi-project.github.io/) now maintains the
[ComicInfo Schema](https://anansi-project.github.io/docs/comicinfo/schemas/v2.1)
and has compatibly and conservatively extended it.

### ComicInfo StoryArcs

Comicbox also supports an unofficial, undocumented Mylar extension to
ComicInfo.xml that encodes multiple Story Arcs and Story Arc Numbers as CSV
values.

| Location      | Name          |
| ------------- | ------------- |
| Archive       | comicinfo.xml |
| Import/Export | comicinfo.xml |

## MetronInfo Schema v1.1

The
[MetronInfo Schema](https://metron-project.github.io/docs/category/metroninfo)
is a new XML schema for comic book metadata, which hopes to improve some of the
deficiencies that exist with the ComicInfo.xml schema.

| Location      | Name           |
| ------------- | -------------- |
| Archive       | metroninfo.xml |
| Import/Export | metroninfo.xml |

### Metron MangaVolume

The MangaVolume tag is a string, and comicbox stores it as one in
`manga_volume`. A value that reads as a single number or a "first-last" range,
like "1-3", also fills in `volume.number` and `volume.number_to`. MangaVolume is
only written from `manga_volume`, never rebuilt from the volume numbers.

### Metron CommunityRating

The v1.1 CommunityRating tag maps to the comicbox `community_rating` object:
AverageRating to `community_rating.average_rating` (which ComicInfo
CommunityRating and ComicBookInfo rating also map to) and RatingCount to
`community_rating.rating_count` (which no other format carries).

### Metron AlternativeNumber

The v1.1 AlternativeNumber tag records a legacy or alternate numbering of the
same issue. It maps to the comicbox `alternative_issue` object, which is parsed
into name, number and suffix parts just like `issue`.

### Metron Reprints and AlternativeNames

A Reprint names another edition of this issue's content and maps to `reprints`.
Series/AlternativeNames are other names the same series goes by — translations,
romanizations, variant spellings — and map to `series.alternative_names`. A
reprint's `name` is stored as the file wrote it; the series, volume and issue
read out of that name are a convenience.

### ComicBookInfo Schema v1.0 (Comic Book Lover)

The schema used by the defunct
[Comic Book Lover](https://bitcartel.neocities.org/comicbooklover/) app. It
supports a few useful tags that ComicInfo.xml does not, but it probably only
survives because Comictagger supports writing it.

I have interpreted the
[ComicBookInfo](https://code.google.com/archive/p/comicbookinfo/wikis/Example.wiki)
example json into a
[ComicBookInfo JSON Schema](https://github.com/ajslater/comicbox/blob/main/schemas/comic-book-info-v1.0.schema.json).

| Location      | Name                 |
| ------------- | -------------------- |
| Archive       | Zip & Rar Comments   |
| Import/Export | comic-book-info.json |

#### ComicBookInfo Role primary attribute

The per-credit `primary` flag is kept, on the role it describes:
`credits.<person>.roles.<role>.primary`.

### PDF XMP Schema

The PDF metadata standard. Written directly to the pdf itself or exported as an
xml file.

[Adobe PDF Namespace](https://developer.adobe.com/xmp/docs/XMPNamespaces/pdf/)
[Adobe PDF Standard](https://opensource.adobe.com/dc-acrobat-sdk-docs/standards/pdfstandards/pdf/PDF32000_2008.pdf)
§ 14.3.3 Document Information Dictionary

PDF metadata is only read or written from and to PDF files.

| Location      | Name             |
| ------------- | ---------------- |
| Archive       | PDF internal     |
| Import/Export | pdf-metadata.xml |

#### Embedding other Metadata Formats in PDF

Comicbox will read and write all the comic metadata file formats it supports for
other kinds of comic archives to PDF embedded files. Comicbox used to optionally
nest this data in the PDF keywords field. Reading other comic metadata from the
PDF keywords fields is still supported. Otherwise the keywords fields is
transformed to and from the "Tags" field.

### CoMet Schema v1.1 (Comic Viewer)

An old and extremely rare comic metadata standard from the defunct
[Comic Viewer](https://www.denvog.com/wordpress/app/comic-viewer/) comic book
reader.

I have interpreted the
[CoMet Specification](http://www.denvog.com/comet/comet-specification/) into a
[CoMet XSD](https://github.com/ajslater/comicbox/blob/main/schemas/CoMet-v1.1.xsd).

| Location      | Name      |
| ------------- | --------- |
| Archive       | comet.xml |
| Import/Export | comet.xml |

### Comicbox 3.0 Schema

The comicbox internal data structure which acts as a superset of the above
schemas to allow interpolating.

[Comicbox 3.0 JSON Schema](https://github.com/ajslater/comicbox/blob/main/schemas/v3.0/comicbox-v3.0.schema.json)

Comicbox 2.0 documents are still read; they are converted to the 3.0 shape on
load. The
[2.0 schema](https://github.com/ajslater/comicbox/blob/main/schemas/v2.0/comicbox-v2.0.schema.json)
is retained unchanged for reference.

#### Comicbox JSON Format

| Location      | Name          |
| ------------- | ------------- |
| Archive       | comicbox.json |
| Import/Export | comicbox.json |

#### Comicbox YAML Format

YAML is a superset of JSON, so the JSON schema applies here.

| Location      | Name          |
| ------------- | ------------- |
| Archive       | comicbox.yaml |
| Import/Export | comicbox.yaml |

#### Comicbox CLI Format

The Comicbox CLI uses "flow style" YAML, which is an all on one line format to
enter metadata on the command line.

Specifying metadata on the command line like this is additive.

| Location      | Name              |
| ------------- | ----------------- |
| Comicbox CLI  | -m --metadata     |
| Archive       | comicbox-cli.yaml |
| Import/Export | comicbox-cli.yaml |
