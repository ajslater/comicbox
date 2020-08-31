# Comicbox

Comicbox is a comic book archive metadata reader and writer. It reads CBR and CBZ archives and writes CBZ archives. It reads and writes the [ComicRack comicinfo.xml format](https://wiki.mobileread.com/wiki/ComicRack#Metadata), the [ComicBookInfo format](https://code.google.com/archive/p/comicbookinfo/) and [CoMet format](https://github.com/wdhongtw/comet-utils).

## API

Comicbox's primary purpose is as a library for other programs with [comicbox.comic_archive](https://github.com/ajslater/comicbox/blob/master/comicbox/comic_archive.py) as the primary interface.

## Console

```sh
comicbox -h
```

to use the CLI.

## Development

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

## Motivation

I didn't like Comictagger's API, so I built this for myself as an educational exercise and to use as a library for [Codex comic reader](https://github.com/ajslater/codex/).

## Alternatives

[Comictagger](https://github.com/comictagger/comictagger) is a better alternative for most purposes at this time. It does everything Comicbox does but also automatically tags comics with the ComicVine API and has a pretty nice desktop UI.

## Future Plans

I may implement ComicVine API tagging, but this library will remain primarily an API for other programs with a console interface.
