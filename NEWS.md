# 📰 News

## v0.3.0

- comicbookinfo changed `critical_rating` to decimal type.
- comicinfo gained the `community_rating` attribute.

## v0.2.2

- Update pycountry to be compatible with codex

## v0.2.1

- Comicbox now raises a specific UnsupportedArchiveTypeError for bad archives

## v0.2.0

- Option for getting the cover image at metadata load time as well.

## v0.1.7

- Remove regex dependancy in favor of re module

## v0.1.6

- Fixed recursive mode trying to operate on directories
- Fix recompressing crash on cbr -> cbz conversion
- Fixed parsing for three new filename patterns
- Updated dependancies

## v0.1.5

- Fix parsing and writing genre, story_arc, series_groups tags

## v0.1.4

- Make metadata read more robust by catching individual tag exceptions and printing them to stdout
- Protect against null people names for credits
- More robust xml volume parsing

## v0.1.3

- Fix cli crash with bad import

## v0.1.2

- Fix relative imports
- Fix credit parsing errors
- Improve 1/2 Issue number parsing

## v0.1.1

- Don't crash import on bad credits

## v0.1.0

- initial release
