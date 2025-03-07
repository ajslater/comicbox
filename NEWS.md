# 📰 News

## v1.2.3

- Fix story arc parsing.

## v1.2.2

- Fix Notes parsing for Comictagger beta Metron origin
- Simplify Identifier URL construction for Metron pk ids.

## v1.2.1

- Fix ignoring MacOS resource forks in archives.
- Detect .jxl extension (JPEG XL) as a comic page.
- Dependency xml parsing fixes and better Python 3.13 support.

## v1.2.0

- Add -R --replace_metadata option. Default behavior is to merge keys.
- Add -D --delete_keys option.
- Faster metadata writing. Replace files in zipfiles instead of rewriting the
  entire archive.

## v1.1.10

- Fix parsing negative issue numbers in filenames.
- Log common non-ComicBookInfo archive comments with less alarm.

## v1.1.9

- Deps security update

## v1.1.8

- Update pycountry

## v1.1.7

- Unknown urls give the path, query and fragment as the nss, not the domain

## v1.1.6

- Ignore dotfiles and macOS resource forks when finding pages.

## v1.1.5

- Fix export of CIX CoverArtist tag.
- Fix tagging Web and other unknown url tags. Accept any url for comicbox
  identifiers.

## v1.1.4

- Make language and country code parsing more durable

## v1.1.3

- Updated comicfn2dict fixes filename parsing bugs.

## v1.1.2

- Fix crash copying directories between archives.
- Fix crash with leftover temp files.

## v1.1.1

- Write ComicInfo.xml in TitleCase so Comictagger can find it.
- Write MetronInfo.xml & CoMet.xml in TitleCase for beauty.
- Fix duplicate reprints.

## v1.1.0

- Fix `--import` option crash.
- Fix parsing tagger and updated_at from notes.
- PDFs read all metadata formats from the keywords field.
- PDFs write ComicInfo.xml to keywords field.
- ComicInfo.xml accepts spaces as web field separator.
- Accept numeric types for issues.
- Major improvements to filename parsing and diversity of filename schemas.

## v1.0.0

- This version contains large breaking changes, some detailed in
  [The 1.0.0 CHANGES document](CHANGES-1.0.0.md)
- Comicbox continues to primarily be an API for reading comic metadata but this
  version contains an enhanced CLI, and more powerful reading, writing,
  synthesis and exporting of metadata.
- Comicbox now sorts archive filenames case insensitively.
- Comicbox now writes identifiers to the notes field in urn format.
- You should probably read the code in `comicbox.box` for public facing apis.
- comicbfn2dict and comicbox-pdffile are now independent packages.

## v0.10.2

- Sophisticated cli metadata parsing. See cli help and README.
  - config.metadata_cli holds the new string format.
- Writing xml and json metadata to files is now pretty printed.
- Fix some instances where falsey values were not written.
- Fix comicinfo.xml ComicPageInfo typing.

## v0.10.1

- Change --metadata cli syntax to use key=\[a,b,c\] for arrays and key=a for
  simple values.

## v0.10.0

- WARNING: Breaking API, CLI & Config changes.
- Write metadata from the command line.
- Optional PDF support. Install as `comicbox[pdf]`
- Python version now >=3.9
- Extract a range of pages from the cli.

## v0.9.1

- Removed dependence on Python 3.11

## v0.9.0

- StoryArc & StoryArcNumber for ComicInfo.xml exported as `story_arcs` dict.
  Supports Mylar multiple story arcs csv values format.

## v0.8.0

- Add close_fd & check_unrar config options for API use.
- Add ComicArchive.check_unrar_executable() public method.
- Remove closefd constructor option.

## v0.7.1

- Remove unrar.cffi support.
- Test for unrar executable for clearer errors.

## v0.7.0

- Fix
  - Tags from ComicInfo.xml were not parsed
- Features
  - ComicInfo.xml StoryArcNumber, Review and GTIN now parsed.
  - ComicInfo.xml Pages attributes now exposed as snake case for python

## v0.6.7

- Fix
  - Remove unrar-cffi dependency aciddentally left in during testing

## v0.6.6

- Features
  - Print filetype cli option. get_archive_type() api method.
  - Use unrar.cffi if it's available.
- Dev
  - Use importlib instead of deprecated pkg_resources.

## v0.6.5

- Feature
  - Demote parser errors to warnings.

## v0.6.4

- Feature --delete-rar option is now --delete-orig
- Fix
  - Fix --delete-rar option sometimes deleting original cbzs

## v0.6.3

- Fix

- Fix rename function renaming files to nothing.
- Fix --dry-run feature for rename.

## v0.6.2

- Fix

  - Enable support for Deflate64.

## v0.6.1

- Fix

  - Fix encoding/decoding crash by replacing uncodable utf-8 characters.

## v0.6.0

- Features

  - Add --metadata cli action. Injects metadata from cli.
  - Warn when no actions performed.
  - == operator for metadata is deep and ignores key order.
  - Credits are now sorted.

- Fix

  - Log format conversions.
  - Don't add empty credits list metadata.

## v0.5.5

- Fix

  - Fix dest-path cli argument.
  - Use defusedxml for XML parsing.
  - Fix recursion crash.
  - Log exception during recursion and proceed.

## v0.5.4

- Fix

  - Remove uneccissary dependencies

## v0.5.3

- Fix

  - Fix filename extension parsing
  - Renamed underscore cli options to use dash instead
  - Fixed crash when recompressing directories.

## v0.5.2

- Features

  - ComicArchive class now has a context manager
  - Removed as_pil() methods for pages and covers

## v0.5.1

- Features

  - Methods for getting covers and pages as PIL Images.
  - Lazy metadata and cover pulling. Removes `metadata` and `cover` options.
  - closefd option leaves archive open after method calls. Close manually with
    close().
  - .cbt Tarfile comic archive support.

## v0.5.0

- Features

  - Issues numbers are now strings.
  - Separate read metadata option from print metadata action.
  - Added dry_run option.
  - Namespace config under "comicbox" map to allow inclusion in caller configs.
  - Allow modnames for local config sources, useful when comicbox is a library.

- Fixes
  - Trap errors reading user config files.
  - Fixed cover extraction to a directory.
  - Abort with message if pages asked to extracted to a filee.
  - Handle more filename patterns.

## v0.4.1 - Yanked

## v0.4.0

- Fixed some file name patterns
- Accept environment variables and config files to configure.
- CLI accepts more than one path as targets for action.
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

- CBI changed `critical_rating` to decimal type from string (in CBI it's an
  int).
- CIX gained the `community_rating` attribute from CIX 2.0 spec.
- `age_rating` replaces `maturity_rating` to standardize more on CIX
- `CoverArtist` replaces `Cover` to standardize more on CIX
- Better CIX `Manga` parsing
- Better CIX `BlackAndWhite` parsing
- Added CIX `AgeRating` valid schema values, unused.
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

- Make metadata read more robust by catching individual tag exceptions and
  printing them to stdout
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
