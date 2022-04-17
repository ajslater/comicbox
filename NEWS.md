# 📰 News

## v0.4.2

- Trap errors reading user config files.
- Allow modnames for local config sources.
- Namespace config under "comicbox" map to allow inclusion in caller configs.
- Added dry_run option.
- Fixed cover extraction to a directory.
- Abort with message if pages asked to extracted to a filee.

## v0.4.1 - Yanked

## v0.4.0

- Fixed some file name patterns
- Accept environment variables and config files to configure.
- CLI accepts multiple arguments as targets for action.
- CLI runs _every_ action on the command line.
- API `get_cover` init variable now set in config as `cover`
- Optional metadata parsing with config.

## v0.3.4

- Fixed combining CBI credits and with other format credits.
- More info in parsing warnings.
- More explicit raw tag titles.

## v0.3.3

- add colored python logging

## v0.3.2

- issue_count type change from decimal to int

## v0.3.1

- Fix synthesizing CBI & CIX credits data.
- Extract decimals from strings for more liberal reading.

## v0.3.0

- CBI changed `critical_rating` to decimal type from string (in CBI it's an int).
- CIX gained the `community_rating` attribute from CIX 2.0 spec.
- `age_rating` replaces `maturity_rating` to standardize more on CIX
- `CoverArtist` replaces `Cover` to standardize more on CIX
- Better CIX `Manga` parsing
- Better CIX `BlackAndWhite` parsing
- Added CIX `AgeRating` valid schema values, unsed.
- LGPL 3.0

## v0.2.2

- Update pycountry to be compatible with codex

## v0.2.1

- Comicbox now raises a specific UnsupportedArchiveTypeError for bad archives

## v0.2.0

- Option for getting the cover image at metadata load time as well.

## v0.1.7

- Remove regex dependency in favor of re module

## v0.1.6

- Fixed recursive mode trying to operate on directories
- Fix recompressing crash on cbr -> cbz conversion
- Fixed parsing for three new filename patterns
- Updated dependencies

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
