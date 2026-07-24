# Comicbox

[![PyPI](https://img.shields.io/pypi/v/comicbox.svg)](https://pypi.org/project/comicbox/)
[![Python](https://img.shields.io/pypi/pyversions/comicbox.svg)](https://pypi.org/project/comicbox/)
[![License](https://img.shields.io/pypi/l/comicbox.svg)](https://github.com/ajslater/comicbox/blob/main/LICENSE)
[![Docs](https://img.shields.io/readthedocs/comicbox)](https://comicbox.readthedocs.io)

Comicbox is a Python library and command line tool that reads, writes, and
synthesizes comic book archive metadata. It understands every popular comic
metadata standard, merges them into one consistent data model, converts between
them, tags comics from online databases, and extracts pages and covers.

It is the metadata engine behind the
[Codex comic reader](https://github.com/ajslater/codex/), but works just as well
as a standalone command line tool for organizing a comic library.

## ✨ What Comicbox Does

- **Reads many archive types** — CBZ, CBR, CBT, CB7, and (optionally) PDF.
- **Reads and writes every popular metadata standard** — ComicInfo.xml,
  MetronInfo.xml, ComicBookInfo, CoMet, PDF metadata, and its own YAML/JSON.
- **Merges every source into one model** — combines metadata from each embedded
  format _and_ the filename into a single normalized view, then writes it back
  out to whichever formats you choose.
- **Tags comics online** — looks up and matches comics against Metron and
  ComicVine, then writes the result.
- **Converts archives** — repacks CBR/CBT/CB7 (and comic PDFs) to CBZ, and
  translates metadata between formats.
- **Extracts images** — pulls cover art or arbitrary page ranges out of any
  supported archive.
- **Is scriptable and embeddable** — a rich CLI, a Python API, and published
  [JSON Schemas](https://comicbox.readthedocs.io/SCHEMAS/) for every format.

### 📚 Archive Formats

| Format    | Read | Write                |
| --------- | :--: | -------------------- |
| CBZ (zip) |  ✅  | ✅                   |
| CBR (rar) |  ✅  | converts to CBZ      |
| CBT (tar) |  ✅  | converts to CBZ      |
| CB7 (7z)  |  ✅  | converts to CBZ      |
| PDF       |  ✅  | ✅ embedded metadata |

CBR extraction and conversion require the `unrar` binary on your `PATH`. PDF
support is an [optional extra](#-installation).

### 🏷️ Metadata Formats

Comicbox reads and writes all of the following, normalizing each into a common
schema:

| Format                                                                                     | Read | Write | Notes                                    |
| ------------------------------------------------------------------------------------------ | :--: | :---: | ---------------------------------------- |
| [ComicInfo.xml](https://anansi-project.github.io/docs/comicinfo/schemas/v2.1) (ComicRack)  |  ✅  |  ✅   | v2.1 (draft) schema                      |
| [MetronInfo.xml](https://metron-project.github.io/docs/category/metroninfo)                |  ✅  |  ✅   | v1.1 schema                              |
| [ComicBookInfo](https://code.google.com/archive/p/comicbookinfo/) (Comic Book Lover)       |  ✅  |  ✅   | archive comment JSON                     |
| [CoMet](https://github.com/wdhongtw/comet-utils)                                           |  ✅  |  ✅   |                                          |
| [PDF metadata](https://pymupdf.readthedocs.io/en/latest/tutorial.html#accessing-meta-data) |  ✅  |  ✅   | can embed ComicInfo.xml / MetronInfo.xml |
| Comicbox YAML / JSON                                                                       |  ✅  |  ✅   | native, lossless                         |
| Filename                                                                                   |  ✅  |   —   | parses metadata out of the file name     |

A full cross-format
[tag translation table](https://comicbox.readthedocs.io/TAGS/) is available.

### 🔀 One Unified Metadata Model

Different formats spell the same idea in different ways. Comicbox reconciles
them so you never have to:

- **Identifiers** — IDs, GTINs, and URLs from every format are aggregated into a
  single `identifiers` structure, and written back out as
  [URNs](https://en.wikipedia.org/wiki/Uniform_Resource_Name) in the Notes
  field.
- **Reprints** — Alternate Names, Aliases, and "is version of" relationships
  collapse into one `reprints` list.
- **Notes mining** — the heavily-abused Notes field is parsed for embedded data
  (tagger, timestamps, and identifiers) that formats don't otherwise carry.
- **Liberal value parsing** — fuzzy, caseless values for enum-like fields (Age
  Rating, Format, credit roles) are accepted, tidied to Title Case, and
  converted to each output format's own enum on write.
- **Filename parsing** — series, issue, year, and more are extracted from a wide
  variety of naming conventions via
  [comicfn2dict](https://github.com/ajslater/comicfn2dict).

### 🌐 Online Tagging

Comicbox can identify a comic and tag it from an online database. **Metron** and
**ComicVine** are supported. It searches by the series, issue, and year it knows
about, ranks candidates, breaks close calls with cover-image matching, and
writes the best result.

```sh
# Interactive: prompts only when the match isn't clear.
comicbox --online metron "GI Joe #007 (1952).cbz"

# Tag by an exact database id (skips searching).
comicbox --id metron:42 "comic.cbz"

# Unattended batch run: never prompts, 4 files at a time.
comicbox --online all --recurse --prompts never -j 4 ./comics/
```

`--match` controls how confidently comicbox writes without asking (`ask` ·
`careful` · `auto` · `eager`), and `--effort` (`minimal` · `balanced` ·
`thorough`) trades matching accuracy for fewer API calls on fan-out sources like
ComicVine — Metron doesn't fan out, so it ignores effort and always searches at
full strength. Credentials come from `--auth`, `COMICBOX_*` environment
variables, the config file, or your system keyring. See `comicbox -h` for the
full set of online, caching, and tuning options.

### 🖼️ Pages, Covers & Conversion

```sh
# Extract the cover image.
comicbox --extract-covers --dest-path ./out "comic.cbz"

# Extract a range of pages (zero-based) by index.
comicbox --extract-pages 0:5 --dest-path ./out "comic.cbz"

# Convert a CBR to a CBZ, carrying metadata across.
comicbox --cbz "comic.cbr"

# Convert a single-image-per-page comic PDF to CBZ without re-encoding.
comicbox --cbz --pdf-pages image "comic.pdf"

# Rename a file to comicbox's canonical filename format.
comicbox --rename "comic.cbz"
```

## 📦 Installation

```sh
pip install comicbox
```

For PDF support, install the `pdf` extra:

```sh
pip install comicbox[pdf]
```

### Dependencies

Comicbox needs no binary dependencies for CBZ, CBT, and CB7. Reading or
converting **CBR** archives requires the `unrar` binary on your `PATH`.

The optional PDF extra pulls in
[pymupdf](https://pymupdf.readthedocs.io/en/latest/installation.html), which
ships wheels with a bundled libmupdf for most platforms. Some platforms (e.g.
Linux on ARM) may need `libstdc++` plus C/C++ build tools to compile it.

#### Installing on ARM (AARCH64)

pymupdf has no pre-built AARCH64 wheels, so pip must build it. On some Python
versions the build fails unless this environment variable is set:

```sh
PYMUPDF_SETUP_PY_LIMITED_API=0 pip install comicbox[pdf]
```

You will also need the `build-essential` and `python3-dev` (or equivalent)
packages.

## ⌨️ Command Line

Comicbox ships a thorough, self-documenting CLI. Run:

```sh
comicbox -h
```

for the complete reference, including every metadata format key, the `--print`
phases, and the online tagging tables. A few representative commands:

```sh
# Print the merged metadata comicbox reads from a comic.
comicbox -p "comic.cbz"

# Set a field and write it as ComicInfo.xml inside the archive.
comicbox -m "{publisher: SmallComics}" -w cix "comic.cbz"

# Recursively set a field across an entire library.
comicbox --recurse -m "{publisher: 'SC Comics'}" -w cix ./comics/

# Export and re-import metadata as a file.
comicbox --export cix "comic.cbz"
comicbox --import ComicInfo.xml -w cix "comic.cbz"
```

`-m`/`--metadata` accepts a compact "linear YAML" using tag names from any of
the supported formats. **Put a space after each colon** so it parses as YAML,
and quote values containing YAML special characters (`:[]{},`). See
`comicbox -h` for many more `-m` examples, and
["escaping YAML"](https://www.w3schools.io/file/yaml-escape-characters/) for the
escaping details.

> 💡 **Preview before writing.** Add `-p` to print exactly what _would_ be
> written, or `-n`/`--dry-run` to perform an action without touching the
> filesystem.

### Editing or Deleting Metadata

The cleanest way to edit or remove existing tags is to round-trip through a
file:

```sh
# 1. Export the current metadata to an editable file.
comicbox --export cix "My Overtagged Comic.cbz"

# 2. Edit it.
nvim ComicInfo.xml

# 3. Preview the re-import.
comicbox --import ComicInfo.xml -p "My Overtagged Comic.cbz"

# 4. Wipe the old tags, then write the edited file back (careful!).
comicbox --delete-all-tags "My Overtagged Comic.cbz"
comicbox --import ComicInfo.xml -w cix "My Overtagged Comic.cbz"
```

You can also drop individual keys with `-D`/`--delete-keys` using dotted glom
paths, e.g. `-D series,reprints.0.series`.

## 🛠 API

Comicbox is primarily a library. The
[`Comicbox`](https://github.com/ajslater/comicbox/blob/main/comicbox/box/__init__.py)
class in `comicbox.box` is the main read interface, and `comicbox.write` exposes
a documented write API. Auto-generated API docs are
[published with the HTML docs](https://comicbox.readthedocs.io).

```python
from comicbox.box import Comicbox

with Comicbox("comic.cbz") as cb:
    metadata = cb.to_dict()  # merged, normalized metadata
    file_type = cb.get_file_type()  # "CBZ", "PDF", ...
    mtime = cb.get_metadata_mtime()  # last metadata modification time
    cover = cb.get_cover_page()  # cover image bytes
```

Writing is done through the public `write_metadata` (single file) and
`bulk_write` (batched) helpers:

```python
from comicbox.write import write_metadata

result = write_metadata(
    "comic.cbz",
    # The patch is the contents under the "comicbox" root tag. The
    # root-wrapped dict Comicbox.to_dict() returns is also accepted.
    {"publisher": {"name": "SmallComics"}, "genres": ["Science Fiction"]},
    formats=["COMIC_INFO"],  # MetadataFormats names; e.g. COMIC_INFO, METRON_INFO
)
print(result.written)
```

Every operational error these APIs raise derives from
`comicbox.exceptions.ComicboxError` — `ArchiveError`, `ArchiveWriteError`,
`MetadataError`, `ExportError`, `WriteValidationError`,
`OnlineConfigurationError`, `OnlineLookupAbortedError`, and
`UnsupportedArchiveTypeError` — so consumers can `except ComicboxError` without
swallowing unrelated programming errors.

## ⚙️ Configuration

Comicbox is configured by command line arguments, an optional config file, and
environment variables (in that order of precedence).

- **Defaults** live in
  [`config_default.yaml`](https://github.com/ajslater/comicbox/blob/main/comicbox/config_default.yaml),
  which also documents the nested config groups (`general`, `read`, `write`,
  `convert`, `compute`, and `online`).
- **Config file** — point at one with `-c PATH`, or place it at
  `~/.config/comicbox/config.yaml`.
- **Environment variables** are prefixed with `COMICBOX_`.
- **Log level** is set with the `LOGLEVEL` environment variable:

```sh
LOGLEVEL=ERROR comicbox -p "comic.cbz"
```

## 📦 Related Packages

Installing comicbox also installs two small sibling libraries, each usable on
its own:

- [comicfn2dict](https://github.com/ajslater/comicfn2dict) — parses metadata out
  of comic filenames into Python dicts (also used by ComicTagger).
- [pdffile](https://github.com/ajslater/pdffile) — presents a `ZipFile`-like
  interface for PDF files (installed with the `[pdf]` extra).

## 📜 Documentation

- [News / changelog](NEWS.md)
- [HTML docs](https://comicbox.readthedocs.io)
- [Metadata schemas](https://comicbox.readthedocs.io/SCHEMAS/)
- [Tag translation table](https://comicbox.readthedocs.io/TAGS/)

## 🛠 Development

Comicbox is hosted on [GitHub](https://github.com/ajslater/comicbox). Most
development tasks are driven by the `Makefile` — run `make` to see what's
available.

The `DEBUG_TRANSFORM` environment variable prints verbose schema-transform
information, useful when debugging format conversions.

## 📄 License

Comicbox is licensed under the
[LGPL-3.0-only](https://github.com/ajslater/comicbox/blob/main/LICENSE) license.
