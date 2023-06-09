# Comicbox

A comic book archive metadata reader and writer.

## ✨ <a href="features">Features</a>

### 📚<a href="comicFormats">Comic Formats</a>

Comicbox reads CBZ, CBR, CBT, and optionally PDF.
Comicbox archives and writes CBZ archives and PDF metadata.

### 🏷️ <a href="metadata_formats">Metadata Formats</a>

Comicbox reads and writes:

- [ComicRack Comicinfo.xml v2.1 (draft)](https://anansi-project.github.io/docs/comicinfo/schemas/v2.1),
  - Also, an unofficial, undocumented Mylar extension to ComicInfo.xml that encodes multiple Story Arcs and Story Arc Numbers as CSV values.
- [ComicBookInfo format](https://code.google.com/archive/p/comicbookinfo/)
- [CoMet format](https://github.com/wdhongtw/comet-utils).
- [PDF Metadata](https://pymupdf.readthedocs.io/en/latest/tutorial.html#accessing-meta-data).
- A variety of filename schemes that encode metadata.

### Usefulness

Comicbox's primary purpose is a library for use by [Codex comic reader](https://github.com/ajslater/codex/).
The API isn't well documented, but you can infer what it does pretty easily here: [comicbox.comic_archive](https://github.com/ajslater/comicbox/blob/main/comicbox/comic_archive.py) as the primary interface.

The command line is increasingly useful and can read and write metadata recursively and extract pages.

### Limitations and Alternatives

Comicbox does _not_ use popular metadata database APIs or have a GUI!

[Comictagger](https://github.com/comictagger/comictagger) is a popular alternative. It does most of what Comicbox does but also automatically tags comics with the ComicVine API and has a desktop UI.

## 📦 <a href="install">Installation</a>

```sh
pip install comicbox
```

Comicbox supports PDFs as an extra when installed like:

```sh
pip install comicbox[pdf]
```

### Dependencies

Comicbox generally works without any binary dependencies but requires `unrar` be on the path to convert CBR into CBZ or extract files from CBRs.

## ⌨️ <a href="usage">Usage</a>

### Console

Type

```sh
comicbox -h
```

see the CLI help.

#### Examples

```sh
comicbox test.cbz -m "Tags=a,b,c" -m "Publisher=SmallComics" -w cr
```

Will write those tags to comicinfo.xml in the archive.

### ⚙️ Config

comicbox accepts command line arguments but also an optional config file
and environment variables.

The variables have defaults specified in
[a default yaml](https://github.com/ajslater/comicbox/blob/main/comicbox/config_default.yaml)

The environment variables are the variable name prefixed with `COMICBOX_`. (e.g. COMICBOX_COMICINFOXML=0)

#### Log Level

change logging level:

```sh
LOGLEVEL=ERROR comicbox -p <path>
```

## 🛠 <a href="development">Development</a>

You may access most development tasks from the makefile. Run make to see documentation.

## 🤔 <a href="motivation">Motivation</a>

I didn't like Comictagger's API, so I built this for myself as an educational exercise and to use as a library for
[Codex comic reader](https://github.com/ajslater/codex/).
