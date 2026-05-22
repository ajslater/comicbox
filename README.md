# Comicbox

A comic book archive metadata reader and writer.

## ✨ Features

### 📚 Comic Formats

Comicbox reads CBZ, CBR, CBT, and optionally PDF. Comicbox archives and writes
CBZ archives and PDF metadata.

### 🏷️ Metadata Formats

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

## 📜 News

Comicbox has a [NEWS file](NEWS.md) to summarize changes that affect users.

## 🕸️ HTML Docs

[HTML formatted docs are available here](https://comicbox.readthedocs.io)

## 📦 Installation

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

## ⌨️ Use

### Related Projects

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

#### Online Tagging

Comicbox can fetch metadata from online comic databases (Metron and ComicVine),
match it against the comic at hand, and write the result.

```sh
# One comic, interactive — comicbox prompts when the match isn't obvious.
comicbox --online metron "GI Joe #007 (1952).cbz"

# Bulk run, unattended — never prompts; ambiguous matches are skipped.
comicbox --online metron,comicvine --prompts never ./comics/ --recurse

# Tag by exact id (skips search entirely).
comicbox --id metron:42 "comic.cbz"

# Constrain a search to a known series id (skips series-discovery API call).
comicbox --online metron --series-id metron:100 "comic.cbz"
```

##### Credentials

Each source needs credentials before it can run. Resolution order is **CLI >
env > config file > keyring**:

| Source    | Required    | Env vars                                       |
| --------- | ----------- | ---------------------------------------------- |
| metron    | user + pass | `COMICBOX_METRON_USER`, `COMICBOX_METRON_PASS` |
| comicvine | key         | `COMICBOX_COMICVINE_KEY`                       |

Or set them on the CLI with the repeatable `--auth <source>:<field>=<value>`
flag:

```sh
comicbox --online metron \
    --auth metron:user=alice \
    --auth metron:pass=secret \
    "comic.cbz"
# (--auth metron:pass=... warns: passwords leak into shell history.)
```

Or set them in `~/.config/comicbox/config.yaml`:

```yaml
comicbox:
    online:
        auth:
            metron:
                user: alice
                pass: secret
            comicvine:
                key: xyz123
```

##### Match-resolution mode

When the match is unambiguous, comicbox writes silently. When it isn't, the
match mode decides whether to prompt, skip, or write anyway.

```sh
# --match: how aggressively to auto-write
#   ask     — never auto-write; prompt on every viable candidate
#   careful — auto-write only when top is unambiguous (clear winner)
#   auto    — careful + auto-write a sole plausible match (default)
#   eager   — auto-write any top above threshold, even with close runner-up

# --prompts never: never prompt; turn would-be prompts into skips
comicbox --online metron --prompts never --match careful ./comics/ # cautious cron
comicbox --online metron --prompts never --match eager ./comics/   # trust the matcher

# The global auto-write threshold:
comicbox --online all --auto-threshold 0.85 ...
```

Per-source overrides for `auto_threshold` and per-source tuning knobs live in
YAML (under `online.tuning.per_source.<source>.*`).

End-of-run summary distinguishes outcomes:

```log
Online tagging summary (24 comics × sources):
  16 auto-written
   3 prompted (chose 2, declined 1)
   3 skipped (matcher declined)
   2 no-match (nothing scored above min_confidence)
```

For the full algorithm and worked examples, see
[tasks/online-tagging/match-resolution-user-doc.md](tasks/online-tagging/match-resolution-user-doc.md).

#### Quirks

##### --metadata parses all formats

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

##### Setting Title when Stories are present

If the metadata contains Stories (MetronInfo.xml only) the title is computed
from the Stories. If you wish to set the title regardless, use the --replace
option. e.g.

```sh
comicbox -m "series: 'G.I. Robot', title: 'Foreign and Domestic'" --replace -p
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

## 🛠 API

Comicbox is mostly used by me in [Codex](https://github.com/ajslater/codex/) as
a metadata extractor. Here's a brief example, but the API remains undocumented.

```python
with Comicbox(path_to_comic) as cb:
  metadata = cb.to_dict()
  page_count = cb.page_count()
  file_type = cb.get_file_type()
  mtime = cb.get_metadata_mtime()
  image_data = car.get_cover_page(pdf_format="pixmap")
```

Attached to these docs in the navigation header there are some auto generated
API docs that might be better than nothing.

### API Example

I don't have many examples yet. But here's one someone asked about on GitHub.

#### Adding a ComicInfo.xml formatted dict to the metadata

```python
from argparse import Namespace

from comicbox.box import Comicbox
from comicbox.transforms.comicinfo import ComicInfoTransform


CBZ_PATH = Path("/Users/GullyFoyle/Comics/DC Comics/Star Spangled War Stories/Star Spangled War Stories (1962) #101.cbz")
CONFIG = Namespace(
   # This config writes comicinfo.xml and also reads comicinfo.xml from the source file.
   # If you don't want to read old data, do not include the read argument.
    comicbox=Namespace(write=["cix"], read=["cix"], compute_pages=False)
)

# You can use any comic metadata format as long as it matches it's transform class.
CIX_DICT = { .... } # A ComicInfo.xml style dict.
# xml dicts are those parsed and emitted by xmltodict https://github.com/martinblech/xmltodict
# read about complex elements with attributes on that page.
SOURCE_TRANSFORM_CLASS = ComicInfoTransform

with Comicbox(CBZ_PATH, config=WRITE_CONFIG) as car:
    car.add_source(CIX_DICT, SOURCE_TRANSFORM_CLASS)
    car.write()   # this will write using the config to the cbz_path.
```

This code would be similar to these command line arguments:

```sh
comicbox --import my-own-comicbox.json --import my-own-comicinfo.xml --write cr "Star Spangled War Stories (1962) #101.cbz"
```

## 📋 Schemas

Comicbox supports most popular comicbook metadata schema definitions. These are
defined on the [SCHEMAS page](SCHEMAS.md).

## 🔀 Tag Translations

A rough [table](TAGS.md) of how Comicbox handles tag translations between
popular comic book metadata formats.

## 🛠 Development

Comicbox code is hosted at [Github](https://github.com/ajslater/comicbox)

You may access most development tasks from the makefile. Run make to see
documentation.

### Environment variables

There is a special environment variable `DEBUG_TRANSFORM` that will print
verbose schema transform information
