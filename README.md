# Comicbox

Comicbox is a comic book archive metadata reader and writer. It reads CBR and CBZ archives and writes CBZ archives. It reads and writes the [ComicRack comicinfo.xml format](https://wiki.mobileread.com/wiki/ComicRack#Metadata), the [ComicBookInfo format](https://code.google.com/archive/p/comicbookinfo/) and [CoMet format](https://github.com/wdhongtw/comet-utils).

## ⌨️ <a href="usage">Usage</a>

### API

Comicbox's primary purpose is as a library for other programs with [comicbox.comic_archive](https://github.com/ajslater/comicbox/blob/master/comicbox/comic_archive.py) as the primary interface.

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

run

```sh
./setup.sh
```

to get started.

To run the code you've checked out

```sh
./run.sh -h
```

will run the comicbox cli.

I'll only merge branches to develop that pass

```sh
./lint.sh
./test.sh
./build.sh
```

And I might require tests for significant new code.

You may automatically fix most simple linting errors with

```sh
./fix-linting.sh
```

## 🤔 <a href="motivation">Motivation</a>

I didn't like Comictagger's API, so I built this for myself as an educational exercise and to use as a library for [Codex comic reader](https://github.com/ajslater/codex/).

## 👍🏻 <a href="alternative">Alternatives</a>

[Comictagger](https://github.com/comictagger/comictagger) is a better alternative for most purposes. It does everything Comicbox does but also automatically tags comics with the ComicVine API and has a pretty nice desktop UI.
