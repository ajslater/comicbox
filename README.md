# Comicbox 

Comicbox is a comic book archive metadata reader and writer. It reads CBR and CBZ archives and writes CBZ archives. It reads and writes the [https://wiki.mobileread.com/wiki/ComicRack#Metadata](ComicRack comicinfo.xml format), the [https://code.google.com/archive/p/comicbookinfo/](ComicBookInfo format) and [https://github.com/wdhongtw/comet-utils](Comet format).

## Motivation

I didn't like Comictagger's API, so I built this for myself as an educational exercise and to use as a library for a forthcoming project.

## Alternatives

[https://github.com/comictagger/comictagger](Comictagger) is a better alternative for most purposes at this time. It does everything Comicbox does but also automatically tags comics with the ComicVine API and has a pretty nice desktop UI.

## Future Plans

I may implement ComicVine API tagging in the futre, but this library will remain primarily an API for other programs with a console interface.
