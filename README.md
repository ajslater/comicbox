# Comicbox 

Comicbox is a comic book archive metadata reader and writer. It reads CBR and CBZ archives and writes CBZ archives. It reads and writes the [ComicRack comicinfo.xml format](https://wiki.mobileread.com/wiki/ComicRack#Metadata), the [ComicBookInfo format](https://code.google.com/archive/p/comicbookinfo/) and [CoMet format](https://github.com/wdhongtw/comet-utils).

## API

Comicbox's primary purpose is as a library for other programs with [comicbox.comic_archive](https://github.com/ajslater/comicbox/blob/master/comicbox/comic_archive.py) as the primary interface.

## Console

```sh
comicbox -h
```

to use the CLI.


## Motivation

I didn't like Comictagger's API, so I built this for myself as an educational exercise and to use as a library for a forthcoming project.

## Alternatives

[Comictagger](https://github.com/comictagger/comictagger) is a better alternative for most purposes at this time. It does everything Comicbox does but also automatically tags comics with the ComicVine API and has a pretty nice desktop UI.

## Future Plans

I may implement ComicVine API tagging, but this library will remain primarily an API for other programs with a console interface.
