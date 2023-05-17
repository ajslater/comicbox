# Comicbox

A comic book archive metadata reader and writer.

## 📚<a href="comicFormats">Comic Formats</a>

Comicbox reads CBZ, CBR, and CBT
archives and writes CBZ archives.

## 🏷️ <a href="metadata_formats">Metadata Formats</a>

Comicbox reads and writes:

- [ComicRack Comicinfo.xml v2.1 (draft)](https://anansi-project.github.io/docs/comicinfo/schemas/v2.1),
  - Also, an unofficial, undocumented Mylar extension to ComicInfo.xml that encodes multiple Story Arcs and Story Arc Numbers as CSV values.
- [ComicBookInfo format](https://code.google.com/archive/p/comicbookinfo/)
- [CoMet format](https://github.com/wdhongtw/comet-utils).
- A variety of filename schemes that encode metadata.

## ⌨️ <a href="usage">Usage</a>

### API

Comicbox's primary purpose is as a library for other programs with [comicbox.comic_archive](https://github.com/ajslater/comicbox/blob/main/comicbox/comic_archive.py) as the primary interface.

### Console

```sh
comicbox -h
```

to use the CLI.

### Config

comicbox accepts command line arguments but also an optional config file
and environment variables.

The variables have defaults specified in
[a default yaml](https://github.com/ajslater/comicbox/blob/master/comicbox/config_default.yaml)

The environment variables are the variable name prefixed with `COMICBOX_`. (e.g. COMICBOX_COMICINFOXML=0)

#### Log Level

change logging level:

```sh
LOGLEVEL=ERROR comicbox -p <path>
```

## 🛠 <a href="development">Development</a>

You may access most development tasks from the makefile. Run make to see documentation.

## Dependencies

Comicbox generally works without any binary dependencies but requires unrar be on the path to convert CBR into CBZ.

## 🤔 <a href="motivation">Motivation</a>

I didn't like Comictagger's API, so I built this for myself as an educational exercise and to use as a library for [Codex comic reader](https://github.com/ajslater/codex/).

## 👍🏻 <a href="alternative">Alternatives</a>

[Comictagger](https://github.com/comictagger/comictagger) is a better alternative for most purposes. It does everything Comicbox does but also automatically tags comics with the ComicVine API and has a pretty nice desktop UI.
