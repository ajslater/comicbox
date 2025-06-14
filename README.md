# Comicbox

A comic book archive metadata reader and writer.

## ✨ <a href="features">Features</a>

### 📚<a href="comicFormats">Comic Formats</a>

Comicbox reads CBZ, CBR, CBT, and optionally PDF. Comicbox archives and writes
CBZ archives and PDF metadata.

### 🏷️ <a href="metadata_formats">Metadata Formats</a>

Comicbox reads and writes:

- [ComicRack ComicInfo.xml v2.1 (draft) schema](https://anansi-project.github.io/docs/comicinfo/schemas/v2.1),
- [Metron MetronInfo.xml v1.0](https://metron-project.github.io/docs/category/metroninfo)
- [Comic Book Lover ComicBookInfo schema](https://code.google.com/archive/p/comicbookinfo/)
- [CoMet schema](https://github.com/wdhongtw/comet-utils).
- [PDF Metadata](https://pymupdf.readthedocs.io/en/latest/tutorial.html#accessing-meta-data).
  - Embedding ComicInfo.xml or MetronInfo.xml inside PDFs.
- A variety of filename schemes that encode metadata.

### Usefulness

Comicbox's primary purpose is a library for use by
[Codex comic reader](https://github.com/ajslater/codex/). The API isn't well
documented, but you can infer what it does pretty easily here:
[comicbox.comic_archive](https://github.com/ajslater/comicbox/blob/main/comicbox/comic_archive.py)
as the primary interface.

The command line can perform most of comicbox's functions including reading and
writing metadata recursively, converting between metadata formats and extracting
pages.

### Limitations and Alternatives

Comicbox does _not_ use popular metadata database APIs or have a GUI!

[Comictagger](https://github.com/comictagger/comictagger) probably the most
useful comicbook tagger. It does most of what Comicbox does but also
automatically tags comics with the ComicVine API and has a desktop UI.

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

#### Base

Comicbox generally works without any binary dependencies but requires `unrar` be
on the path to convert CBR into CBZ or extract files from CBRs.

#### PDF

The pymupdf dependency has wheels that install a local version of libmupdf. But
for some platforms (e.g. Linux on ARM, Windows) it may require libstdc++ and
c/c++ build tools installed to compile a libmupdf. More detail on this is
available in the
[pymupdf docs](https://pymupdf.readthedocs.io/en/latest/installation.html#installation-when-a-suitable-wheel-is-not-available).

##### Installing Comicbox on ARM (AARCH64) with Python 3.13

Pymupdf has no pre-built wheels for AARCH64 so pip must build it and the build
fails on Python 3.13 without this environment variable set:

```sh
PYMUPDF_SETUP_PY_LIMITED_API=0 pip install comicbox
```

You will also have to have the `build-essential` and `python3-dev` or equivalent
packages installed on on your Linux.

## ⌨️ <a href="usage">Usage</a>

##### Related Projects

Comicbox makes use of two of my other small projects:

[comicfn2dict](https://github.com/ajslater/comicfn2dict) which parses metadata
in comic filenames into python dicts. This library is also used by Comictagger.

[pdffile](https://github.com/ajslater/pdffile) which presents a ZipFile like
interface for PDF files.

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

Be sure to add spaces after colons so they parse as valid YAML key value pairs.
This is easy to forget.

But it's probably better to use the --print action to see what it's going to do
before you actually write to the archive:

<!-- eslint-skip -->

```sh
comicbox test.cbz -m "{Tags: a,b,c, story_arcs: {d:1,e:'',f:3}" -m "Publisher: SmallComics" -p
```

A recursive example:

<!-- eslint-skip -->

```sh
comicbox --recurse -m "publisher: 'SC Comics'" -w cr ./SmallComicsComics/
```

Will recursively change the publisher to "SC Comics" for every comic found in
under the SmallComicsComics directory.

#### Escaping YAML

the `-m` command line argument accepts the YAML language for tags. Certain
characters like `\,:;_()$%^@` are part of the YAML language. To successful
include them as data in your tags, look up
["Escaping YAML" documentation online](https://www.w3schools.io/file/yaml-escape-characters/)

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
comicbox --delete-all-tags "My Overtagged Comic.cbz"
# Import the metadata into the file and write it.
comicbox --import comicinfo.xml --write cix "My Overtagged Comic.cbz"
```

#### Quirks

##### --metadata parses all formats.

The comicbox.yaml format represents the ComicInfo.xml Web tag as sub an
`identifiers.<NID>.url` tag. But fear not, you don't have to remember this. The
CLI accepts heterogeneous tag types with the `-m` option, so you can type:

<!-- eslint-skip -->

```sh
comicbox -p -m "Web: https://foo.com" mycomic.cbz
```

and the identifier tag should appear in comicbox.yaml as:

```yaml
identifiers:
  foo.com:
    id_key: ""
    url: https://foo.com
```

You don't even need the root tag.

##### Setting Title when Stories are present.

If the metadata contains Stories (MetronInfo.xml only) the title is computed
from the Stories. If you wish to set the title regardless, use the --replace
option. e.g.

```sh
comicbox -m "series: 'G.I. Robot', title: 'Foreign and Domestic'" -Rp
```

But be aware it will also create a story with the title's new name.

##### Identifiers

Comicbox aggregates IDS, GTINS and URLS from other formats into a common
Identifiers structure.

##### Reprints

Comicbox aggregates Alternate Names, Aliases and IsVersionOf from other formats
into a common Reprints list.

##### URNs

Because the Notes field is commonly abused in ComicInfo.xml to represent fields
ComicInfo does not (yet?) support comicbox parses the notes field heavily
looking for embedded data. Comicbox also writes identifiers into the Notes field
using an
[Uniform Resource Name](https://en.wikipedia.org/wiki/Uniform_Resource_Name)
format.

Comicbox also looks for identifiers in Tag fields of formats that don't have
their own Identifiers field.

##### Prettified Fields

Comicbox liberally accepts all kinds of values that may be enums in other
formats, like AgeRating, Formats and Creidit Roles. In a weak attempt to
standardize these values comicbox will Title case values submitted to these
fields. When writing to standard formats, comicbox attempts to transforms these
values into enums supported by the output format.

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

The filename parser is available as a separate library:
[comicfn2dict](https://github.com/ajslater/comicfn2dict)

| Location      | Name                  |
| ------------- | --------------------- |
| Archive       | The archive filename  |
| Import/Export | comicbox-filename.txt |

### ComicInfo Schema v2.1 Draft (Comic Rack)

This schema used by the defunct Comic Rack reader is the de facto standard for
comic book metadata on the internet. The
[Anansi Project](https://anansi-project.github.io/) now maintains the
[ComicInfo Schema](https://anansi-project.github.io/docs/comicinfo/schemas/v2.1)
and has compatibly and conservatively extended it.

#### ComicInfo StoryArcs

Comicbox also supports an unofficial, undocumented Mylar extension to
ComicInfo.xml that encodes multiple Story Arcs and Story Arc Numbers as CSV
values.

| Location      | Name          |
| ------------- | ------------- |
| Archive       | comicinfo.xml |
| Import/Export | comicinfo.xml |

### MetronInfo Schema v1.0

The
[MetronInfo Schema](https://metron-project.github.io/docs/category/metroninfo)
is a new XML schema for comic book metadata, which hopes to improve some of the
deficiencies that exist with the ComicInfo.xml schema.

| Location      | Name           |
| ------------- | -------------- |
| Archive       | metroninfo.xml |
| Import/Export | metroninfo.xml |

#### Metron MangaVolume

The MangaVolume tag is interpreted not as an arbitrary string, but as a range of
integers delineated by a "-". e.g "1-3".

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

Comicbox discards the <Role primary/> attribute.

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

### ComicTagger Schema

The most useful general comic book metadata writer is
[ComicTagger](https://github.com/comictagger/comictagger). It supports the
ComicVine API, is extensible to other APIs, and features a nice desktop GUI.
Internally, Comictagger keeps a metadata object to work with the schemas it
supports. This schema allows the import and export of that schema.

[Comictaggger genericmetadata.py](https://github.com/comictagger/comictagger/blob/develop/comicapi/genericmetadata.py)

This schema is possibly only useful to developers using the API to import and
export python dicts, but the capability to import an export this format json
format as json exists. The author of ComicTagger offers no promises as to the
stability of this API and I am very lazy, so the chances of this drifting out of
date are anyone's guess. It was included because it was easy to do.

| Location      | Name             |
| ------------- | ---------------- |
| Archive       | comictagger.json |
| Import/Export | comictagger.json |

### Comicbox 2.0 Schema

The comicbox internal data structure which acts as a superset of the above
schemas to allow interpolating.

[Comicbox 2.0 JSON Schema](https://github.com/ajslater/comicbox/blob/main/schemas/v2.0/comicbox-v2.0.schema.json)

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

## Environment variables

There is a special environment variable `DEBUG_TRANSFORM` that will print
verbose schema transform information
