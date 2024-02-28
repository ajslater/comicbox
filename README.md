# Comicbox

A comic book archive metadata reader and writer.

## ✨ <a href="features">Features</a>

### 📚<a href="comicFormats">Comic Formats</a>

Comicbox reads CBZ, CBR, CBT, and optionally PDF. Comicbox archives and writes
CBZ archives and PDF metadata.

### 🏷️ <a href="metadata_formats">Metadata Formats</a>

Comicbox reads and writes:

- [ComicRack ComicInfo.xml v2.1 (draft) schema](https://anansi-project.github.io/docs/comicinfo/schemas/v2.1),
- [Comic Book Lover ComicBookInfo schema](https://code.google.com/archive/p/comicbookinfo/)
- [CoMet schema](https://github.com/wdhongtw/comet-utils).
- [PDF Metadata](https://pymupdf.readthedocs.io/en/latest/tutorial.html#accessing-meta-data).
  - Embedding ComicInfo.xml inside PDFS.
- A variety of filename schemes that encode metadata.

### Usefulness

Comicbox's primary purpose is a library for use by
[Codex comic reader](https://github.com/ajslater/codex/). The API isn't well
documented, but you can infer what it does pretty easily here:
[comicbox.comic_archive](https://github.com/ajslater/comicbox/blob/main/comicbox/comic_archive.py)
as the primary interface.

The command line is increasingly useful and can read and write metadata
recursively and extract pages.

### Limitations and Alternatives

Comicbox does _not_ use popular metadata database APIs or have a GUI!

[Comictagger](https://github.com/comictagger/comictagger) is a popular
alternative. It does most of what Comicbox does but also automatically tags
comics with the ComicVine API and has a desktop UI.

## 📦 <a href="install">Installation</a>

<!-- eslint-skip -->

```sh
pip install comicbox
```

Comicbox supports PDFs as an extra when installed like:

<!-- eslint-skip -->

```sh
pip install comicbox[pdf]
```

### Dependencies

Comicbox generally works without any binary dependencies but requires `unrar` be
on the path to convert CBR into CBZ or extract files from CBRs.

## ⌨️ <a href="usage">Usage</a>

### Console

Type

<!-- eslint-skip -->

```sh
comicbox -h
```

see the CLI help.

#### Examples

<!-- eslint-skip -->

```sh
comicbox test.cbz -m "{Tags: a,b,c, story_arcs: {d:1,e:'',f:3}" -m "Publisher: SmallComics" -w cr
```

Will write those tags to comicinfo.xml in the archive.

Be sure to add spaces after colons so they are detected as valid YAML key value
pairs. This is easy to forget.

But it's probably better to use the --print action to see what it's going to do
before you actually write to the archive:

<!-- eslint-skip -->

```sh
comicbox test.cbz -m "{Tags: a,b,c, story_arcs: {d:1,e:'',f:3}" -m "Publisher: SmallComics" -p
```

A recursive example:

<!-- eslint-skip -->

```sh
comicbox --recurse -m "publisher: SC Comics" -w cr ./SmallComicsComics/
```

Will recursively change the publisher to "SC Comics" for every comic found in
under the SmallComicsComics directory.

##### Deleting Metadata

To delete metadata from the cli you're best off exporting the current metadata,
editing the file and then re-importing it with the delete previous metadata
option:

<!-- eslint-skip -->

```sh
# export the current metadata
comicbox --export cix "My Overtagged Comic.cbz"
# Adjust the metadata in an editor.
nvim comicinfo.xml
# Check that importing the metadata will look how you like
comicbox --import comicinfo.xml -p "My Overtagged Comic.cbz"
# Delete all previous metadata from the comic (careful!)
comicbox --delete "My Overtagged Comic.cbz"
# Import the metadata into the file and write it.
comicbox --import comicinfo.xml --write cix "My Overtagged Comic.cbz"
```

#### Packages

Comicbox actually installs three different packages:

- `comicbox` The main API and CLI script.
- `comicfn2dict` A separate library for parsing comic filenames into dicts it
  also includes a CLI script.
- `pdffile` A utility library for reading and writing PDF files with an API like
  Python's ZipFile

### ⚙️ Config

comicbox accepts command line arguments but also an optional config file and
environment variables.

The variables have defaults specified in
[a default yaml](https://github.com/ajslater/comicbox/blob/main/comicbox/config_default.yaml)

The environment variables are the variable name prefixed with `COMICBOX_`. (e.g.
COMICBOX_COMICINFOXML=0)

#### Log Level

change logging level:

<!-- eslint-skip -->

```sh
LOGLEVEL=ERROR comicbox -p <path>
```

## 🛠 <a href="development">Development</a>

You may access most development tasks from the makefile. Run make to see
documentation.

## 🤔 <a href="motivation">Motivation</a>

I didn't like Comictagger's API, so I built this for myself as an educational
exercise and to use as a library for
[Codex comic reader](https://github.com/ajslater/codex/).

## 📋 <a href="schemas">Schemas</a>

Comicbox supports reading and writing several comic book metadata schemas.

### Filename Schema

Comicbox includes a pretty good comic archive filename parser. It can extract a
number of common fields from comic archive filenames.

| Location      | Name                  |
| ------------- | --------------------- |
| Archive       | The archive filename  |
| Import/Export | comicbox-filename.txt |

### PDF Schema

The pdf metadata standard. Can be exported as an xml file or written directly to
the pdf itself.

[Adobe PDF Namespace](https://developer.adobe.com/xmp/docs/XMPNamespaces/pdf/)
[Adobe PDF Standard](https://opensource.adobe.com/dc-acrobat-sdk-docs/standards/pdfstandards/pdf/PDF32000_2008.pdf)
§ 14.3.3 Document Information Dictionary

PDF metadata is only read or written from and to PDF files.

| Location      | Name             |
| ------------- | ---------------- |
| Archive       | PDF internal     |
| Import/Export | pdf-metadata.xml |

#### Reading Embedded Metadata from `keywords`

Comicbox will read most any metadata standard it supports from the keywords
field. If that fails it will consider the keywords field as a comma delimited
"Tags" field.

#### Writing ComicInfo.xml to `keywords`

By default Comicbox will write ComicInfo XML to the keywords field (e.g.
`-w pdf`)

[Codex](https://github.com/ajslater/codex) supports this because it uses
Comicbox. Other comic readers do not support PDF embedded ComicInfo.xml, but
since they already have ComicInfo.xml parsers it's possible that they might
someday.

If Comicbox JSON is included in the write formats (e.g. `-w pdf,json`) Comicbox
will write comicbox.json to the keywords field instead. It is unlikely that any
other comic reader other than Codex will ever support this.

### CoMet Schema

An old and uncommon comic metadata standard from a defunct comic book reader.

[CoMet Specification](http://www.denvog.com/comet/comet-specification/)

| Location      | Name      |
| ------------- | --------- |
| Archive       | comet.xml |
| Import/Export | comet.xml |

### ComicBookInfo Schema (Comic Book Lover)

The Comic Book Lover schema. A rare but still encountered JSON schema. It
probably survives because Comictagger supports writing it.

[ComicBookInfo](https://code.google.com/archive/p/comicbookinfo/wikis/Example.wiki)

| Location      | Name                 |
| ------------- | -------------------- |
| Archive       | Zip & Rar Comments   |
| Import/Export | comic-book-info.json |

### ComicInfo Schema (Comic Rack)

The Comic Rack schema. The de facto standard of comic book metadata. The Comic
Rack reader is defunct, but the
[Anansi Project](https://anansi-project.github.io/) now publishes the ComicInfo
spec and has compatibly and conservatively extended it.

[Anansi ComicInfo v2.1 Spec](https://anansi-project.github.io/docs/comicinfo/schemas/v2.1)
Also, an unofficial, undocumented Mylar extension to ComicInfo.xml that encodes
multiple Story Arcs and Story Arc Numbers as CSV values.

| Location      | Name          |
| ------------- | ------------- |
| Archive       | comicinfo.xml |
| Import/Export | comicinfo.xml |

### ComicTagger Schema

The most useful comic book metadata writer is
[ComicTagger](https://github.com/comictagger/comictagger). It supports the
ComicVine API, is extensible to other APIs, and features a nice desktop GUI.
Internally, Comictagger keeps a metadata object to work with the schemas it
supports. This schema allows the import and export of that schema.

[Comictaggger genericmetadata.py](https://github.com/comictagger/comictagger/blob/develop/comicapi/genericmetadata.py)

This schema may only be useful to developers. The author of ComicTagger offers
no promises as to the stability of this API and I am very lazy, so the chances
of this drifting out of date are anyone's guess. It was included because it was
easy to do.

| Location      | Name             |
| ------------- | ---------------- |
| Archive       | comictagger.json |
| Import/Export | comictagger.json |

### Comicbox Schema

The comicbox internal data structure which acts as a superset of the above
schemas to allow interpolating.

[Comicbox JSON Schema](https://github.com/ajslater/comicbox/blob/main/schemas/comicbox.schema.json)

#### JSON Format

| Location      | Name          |
| ------------- | ------------- |
| Archive       | comicbox.json |
| Import/Export | comicbox.json |

#### YAML Format

YAML is a superset of JSON, so the JSON schema applies here.

| Location      | Name          |
| ------------- | ------------- |
| Archive       | comicbox.yaml |
| Import/Export | comicbox.yaml |

#### CLI Format

The Comicbox CLI uses "flow style" YAML, which is an all on one line format to
enter metadata on the command line.

Specifying metadata on the command line like this is additive.

| Location      | Name              |
| ------------- | ----------------- |
| Comicbox CLI  | -m --metadata     |
| Archive       | comicbox-cli.yaml |
| Import/Export | comicbox-cli.yaml |

## Environment variables

There is a special environment variable `DEBUG_TRANSFORM` that will print
verbose schema transform information
