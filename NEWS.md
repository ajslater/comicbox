# 📰 News

## v4.5.1

- Features
    - Extracting a range of PDF pages as PDFs now writes one PDF of the whole
      range instead of a file per page.

- Fixes
    - Default PDF to CBZ conversion produced an archive of raw `.ppm` pixmaps
      that comic readers (including comicbox itself) do not recognize as pages,
      yielding a zero page book — and `--delete-orig` then removed the working
      original. Conversion now defaults to `pixmap_jpeg` whole-page renders,
      which also apply pdf display rotation.
    - `--pdf-pages image` extraction and conversion wrote rotated pages as
      stored — sideways or upside down for scans that rely on `/Rotate` (or a
      rotated content-stream placement) for display. Rotated image-dominant
      pages are now rendered to match the displayed orientation; unrotated pages
      still extract their original bytes untouched.
    - Converted pdf pages are now stored uncompressed in the zip like other
      images; the compression decision previously ran before pages gained their
      image suffix, so page images were pointlessly deflated.
    - The `--pdf-pages` help lists exactly the values it accepts. It advertised
      `pdf` where unsupported and omitted `image_if_dominant` and `pixmap_jpeg`.
    - A PDF with embedded metadata (e.g. a written ComicInfo.xml) no longer
      counts that file as an extra page, which inflated the page count and left
      a stray file when extracting page ranges.
    - Extracted PDF pages are named for their contents. Pages extracted as
      images were given a `.pdf` suffix.

## v4.5.0

- Features
    - The public write API can now clear fields: `write_metadata()` and
      `BulkWriteItem` accept `delete_keys`, glom key paths removed from the
      final metadata before writing (layered onto the config's
      `general.delete_keys`). Empty patch values are pruned on schema load, so
      previously an update-mode write could never clear an existing tag. The
      patch may be empty when `delete_keys` is non-empty (a pure-clear write).

## v4.4.0

- Features
    - Support the MetronInfo.xml v1.1 schema: new AlternativeNumber and
      CommunityRating (AverageRating, RatingCount) tags.
    - New comicbox `community_rating` field (average\_rating, rating\_count).
      ComicInfo CommunityRating and ComicBookInfo rating now map to it instead
      of `critical_rating`, which remains but no longer maps to any format.
    - New comicbox `alternative_issue` field, parsed into name, number and
      suffix parts like `issue`. The Metron API alt\_number now maps to it
      instead of the issue suffix.
    - Metron online tagging now fills `community_rating` from the API's
      average\_rating and rating\_count (mokkari 4.2.0).

## v4.3.0

- Features
    - `OnlineSession.rate_limit_status()` is no longer a stub: Metron entries
      now report the account's live rate-limit budget (burst and daily sustained
      windows — limit, remaining, and reset epoch) that mokkari 4 tracks from
      `X-RateLimit-*` response headers. The daily limit varies by Metron
      OpenCollective donor tier, so this is the only place it's discoverable.
      Comic Vine still reports `{}`; simyan exposes no budget to read. Host
      applications (e.g. Codex) can poll this during a batch run to display live
      budget.

## v4.2.0

- Config
    - Custom Metron rate limits (per\_minute/per\_day) in the config are no
      longer supported and will be ignored in favor of the limits Metron reports
      for your account — mokkari 4 reads them from API response headers, so
      higher OpenCollective donor tiers are picked up automatically. You will
      see a warning if you still have them set. These keys are deprecated for
      every source and will be removed in a future release.
    - `--jobs` is capped at 20 (Metron's burst limit) when Metron is an active
      credentialed source for the run; the log explains the cap when it engages.

- Fixes
    - Rate-limited API responses missing a `Retry-After` header now back off on
      the normal schedule instead of retrying immediately.
    - Ignored-config warnings (rate-limit overrides, `--api-url` for Metron) now
      print once per run instead of once per file.

## v4.1.1

- Performance
    - Upgraded Simyan, the ComicVine API library, for more accurate wait-time
      estimates, fewer hangs, and automatic background cleanup of old cached
      data.

- Config
    - Custom ComicVine rate limits (per\_second/per\_hour) in the config are no
      longer supported and will be ignored in favor of the official limits. You
      will see a warning if you still have them set.

## v4.1.0

- Features
    - Batch API callers can project the API-request count and duration of an
      online-tag run via `comicbox.online_session.estimate_run()`, so the
      request model lives with the search flow it describes.

## v4.0.5

- Performance
    - Metron online tagging now identifies an issue in far fewer API requests —
      often one or two instead of dozens — so tagging is faster and more
      reliable. Courtesy of @bpepple. The --effort option no longer applies to
      Metron due to this improved API.

## v4.0.4

- Fixes
    - Online tagging now searches using embedded metadata (e.g. series name)
      instead of the filename when both are present, so already-tagged comics
      match more accurately.
    - Renaming no longer crashes when metadata contains a path separator (e.g. a
      slash in the series or title); the separator becomes `_` in the name.

## v4.0.3

- Features
    - Add Sweet Shop kebab case filename format. Courtesy of @bpepple.

- Fixes
    - Online cover matching now works for PDFs; the cover page is rasterized
      before perceptual hashing instead of handing raw PDF bytes to the image
      hasher. Courtesy of @bpepple.
    - Security release for dependencies.

## v4.0.2

- Fixes
    - CBR files whose RAR entries carry sub-microsecond timestamps no longer
      break the `ProcessPoolExecutor` worker pool. `rarfile`'s `nsdatetime` is
      an unpicklable `datetime` subclass; its mtime is now coerced to a plain
      `datetime` so results survive transfer back from worker processes.

## v4.0.1

- Fixes
    - A source's web URL no longer clobbers its authoritative `<ID>`/GTIN
      identifier key on read. Metron/Comic Vine ids now survive a write→read
      round trip in ComicInfo and MetronInfo, so already-tagged comics refresh
      via their stored id instead of falling through to a full online search.
    - Metron url parsing no longer captures a trailing slash into the id key
      (`.../issue/123495/` -> `123495`, not `123495/`).
    - The `AutoWritten` event now fires for matches resolved by explicit id or
      stored id, so it reports a source for every auto-written comic.

## v4.0.0 - Online Metadata Tagging

- 🚨 Breaking Changes
    - Removed the ComicTagger (`comictagger.json`) format.
    - Reorganized config files into nested groups (`general`, `read`, `write`,
      `convert`, `online`, …). Flat v3 config files must be migrated.
    - Dry-run is now `-n` (was `-y`).
    - PDFs no longer decode comicbox metadata hidden in the PDF `keywords`
      field; `keywords` now reads as plain tags. Metadata embedded as files
      inside a PDF still reads normally.
    - Library API: `Comicbox(...)` no longer accepts a `logger=` argument and
      never reconfigures the host application's logging. Host apps keep their
      own loguru sinks; the CLI configures its own.
    - Library API: operational errors derive from
      `comicbox.exceptions.ComicboxError` (`ArchiveError`, `MetadataError`,
      `ExportError`, …) instead of raising bare `ValueError`. Consumers can
      `except ComicboxError`.
- Fixes
    - Normalize ComicBookInfo `rating` to the canonical 0-5 scale.
    - Map Metron price currencies to the correct country.
    - Harden credentials against accidental leaks into logs.
    - `write_metadata()` accepts the root-wrapped dict `to_dict()` returns;
      passing it used to silently write nothing while reporting success.
    - Metadata added with `add_metadata()` after a read is no longer ignored.
    - `to_dict()` computes pages and page count correctly when one instance
      dumps multiple formats.
    - Exported metadata files no longer end with a trailing blank line.
- Features
    - Online metadata tagging from Metron and ComicVine with `--online`.
      Comicbox searches by the comic's series, issue, and year, ranks the
      candidates, breaks close calls with cover-image matching, and writes the
      best match.
        - `--match {ask | careful | auto | eager}` sets how confidently a match
          is written without asking; `--prompts never` turns prompts into skips
          for cron and batch runs.
        - `--id <db>:<id>` tags by an exact upstream id; `--series-id <db>:<id>`
          constrains a search to a known series.
        - Credentials resolve from `--auth`, `COMICBOX_*` environment variables,
          the config file, or the system keyring.
        - Online responses are cached on disk (`--cache`, `--cache-ttl`);
          `--effort` trades API calls for matching accuracy.
    - Process many files in parallel with `-j N`, including batch online
      tagging.
    - New public write API: `comicbox.write.write_metadata` and `bulk_write`.
- Performance
    - Faster archive reads: the 7z and RAR backends load lazily, the page list
      is derived from cached archive state, and that state is released on
      `close()`.

## v3.0.3

- Fix small crashes with metron credits and comicbox with no path

## v3.0.2

- Use new comicfn2dict. Parses more comic filename variations.

## v3.0.1

- Require new comicbox-pdffile that doesn't corrupt PDF pages. Includes
  image-dominant page detection (`PDFFile.classify_page`,
  `PDFFile.read_image_if_dominant`, `PDFFile.read_full_pixmap_jpeg`) used by
  browser readers to serve scanned-comic PDF pages as plain `<img>`.

## v3.0.0 - Config Dataclass & Parallel Reads

- Breaking Changes
    - get\_config() now returns a ComicboxSettings dataclass, not a Confuse
      AttrDict. Comicbox constructor now accepts this dataclass instead of an
      AttrDict
- Fixes
    - Stop emitting `metron.cloud/{genre,location,reprint,role,story,tag}/...`
      URLs for Metron identifiers — those paths 404 because Metron has no public
      web pages for those types (only API endpoints). The numeric Metron ID is
      still preserved on the identifier.
    - Security against suspicious archive paths when extracting pages and
      metadata to the filesystem.
- Performance
    - Reducing startup time for new instances of comicbox.
    - General performance improvements for reading metadata from many files.
    - Special multiprocessing and async methods
      comicbox.process.iter\_process\_files() and
      comicbox.process.aread\_metadata() for reading large batches of files at
      once.
    - `Comicbox.get_cover_page(skip_metadata=True)` skips metadata parsing for
      callers that just need the first archive image as a thumbnail. Removes
      per-call schema instantiation and Union resolution overhead.
- Features
    - Add Age Rating conversion function
      comicbox.enums.maps.to\_metron\_age\_rating(value: str | Enum) ->
      MetronAgeRatingEnum | None

## v2.2.3

- Update marshmallow & rich

## v2.2.2

- Update deepdiff library

## v2.2.1

- Fix reading PDF metadata breaking on datetimes.
- PDF datetime parsing failures are warned about instead of raising an exception
  and abandoning parsing.

## v2.2.0

- Add `--pdf-page-format` option to choose how pdf pages are extracted. Replaces
  `to_pixmap` in the API.
- `--cbz` now works on PDF files. Can create original image CBZs with
  `--pdf-page_format image` for PDFs with single image pages.
- `--validate` validates imported and archive metadata against available schemas
- `--import` expands quoted "glob\*" paths.
- Fix comicbox jsonschema.
- Many more type annotations. Include py.typed sentinel file.

## v2.1.1

- Pin confuse config library at 2.1.0 due to typing issues with 2.2.0
- YAML formats now dump unquoted date and datetimes.

## v2.1.0

- PDFs now write to pdf embedded files instead of overloading the metadata
  keywords field. Thanks for the idea from @bpepple
    - PDFS still read full metadata formats from the keywords field if they
      exist for backward compatibility.
- Read more flexible datetimes from PDFs

## v2.0.6

- Python 3.14 support.

## v2.0.5

- Fix a crash when dumping comicbox.json format with only one page.

## v2.0.4

- The confuse library dependency doesn't support Python 3.14. So neither does
  comicbox :(

## v2.0.3

- Fix ComicInfo.xml coercing Age Rating to wrong value.
- Normalize more original\_format names.
- Update xmltodict. Removes much comicbox fix code.

## v2.0.2

- Ensure mtimes from archives are timezone aware.
- More aliases for comicvine identifier source.
- Make archive comments that aren't ComicBookInfo JSON log as debug comments
  more often.

## v2.0.1

- Resolve circular import if not installed with \[pdf] option.

## v2.0.0

### 🚨 BREAKING CHANGES 🚨

- Schema, API, config and CLI changes. See
  [the 2.0 CHANGES document](CHANGES-2.0.0.md).

### Features

#### File Formats

- CB7 archive read support. Comic archives in 7zip archives.

#### Schemas

- Support the MetronInfo.xml v1.0 Schema
- Add AniList, Kitsu, MangaDex, MangaUpdates, MyAnimeList identifier sources.
- ComicInfo.xml gains the `Translator` tag
- PDF `modDate` is now read and written.
- URNs as serialized identifiers in `notes` tag gain an optional tag type
  attribute in the nss: e.g. `urn:comicvine:series:1234`
- Comictagger schema supports series\_aliases and title\_aliases as reprints
- Parse PDF datetime format.
- Many enum fields now accept caseless and slightly fuzzy value lookups that are
  coerced to correct types for the specified output metadata format.
- For convenience, named or numbered types or collections in the comicbox schema
  may also be parse by their simple name instead of requiring a complex object.

#### Config

- `--delete action` becomes `--delete-all-tags`.
- `--compute-pages` is off by default. Turn on to recompute ComicInfo style
  `Pages` structures
- `--no-compute-page-count` prevents recomputing page\_count.
- `--delete_keys` now excludes keys from loading entirely.
- Syntax highlighting used on output. Change or remove with `--theme` option.

#### Fixes

- ComicInfo.xml StoryArcs tag was not loaded.
- Fix proper lowercasing of serialized boolean values in xml attributes.
- ComicBookInfo `issue` tag becomes an integer.
- Fix ISBN & UPC url detection
- ComicInfo.xml orders tags properly per the xsd.
- Corrected schemaLocation tags for xml formats to be valid.
- ComicBookInfo.json `rating`, and `tags` tags fixed.
- Support ComicBookInfo.json `primary` credit tag.
- More accurate merging of different metadata sources.

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

- Add -R --replace\_metadata option. Default behavior is to merge keys.
- Add -D --delete\_keys option.
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
- Fix parsing tagger and updated\_at from notes.
- PDFs read all metadata formats from the keywords field.
- PDFs write ComicInfo.xml to keywords field.
- ComicInfo.xml accepts spaces as web field separator.
- Accept numeric types for issues.
- Major improvements to filename parsing and diversity of filename schemas.

## v1.0.0

- 🚨 This version contains large breaking changes 🚨
    - Some are detailed in [The 1.0.0 CHANGES document](CHANGES-1.0.0.md)
- Comicbox continues to primarily be an API for reading comic metadata but this
  version contains an enhanced CLI, and more powerful reading, writing,
  synthesis and exporting of metadata.
- Comicbox now sorts archive filenames case insensitively.
- Comicbox now writes identifiers to the notes field in urn format.
- You should probably read the code in `comicbox.box` for public facing apis.
- comicbfn2dict and comicbox-pdffile are now independent packages.

## v0.10.2

- Sophisticated cli metadata parsing. See cli help and README.
    - config.metadata\_cli holds the new string format.
- Writing xml and json metadata to files is now pretty printed.
- Fix some instances where falsey values were not written.
- Fix comicinfo.xml ComicPageInfo typing.

## v0.10.1

- Change --metadata cli syntax to use key=\[a,b,c] for arrays and key=a for
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

- Add close\_fd & check\_unrar config options for API use.
- Add ComicArchive.check\_unrar\_executable() public method.
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
    - Print filetype cli option. get\_archive\_type() api method.
    - Use unrar.cffi if it's available.
- Dev
    - Use importlib instead of deprecated pkg\_resources.

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
    - \== operator for metadata is deep and ignores key order.
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
    - Removed as\_pil() methods for pages and covers

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
    - Added dry\_run option.
    - Namespace config under "comicbox" map to allow inclusion in caller
      configs.
    - Allow modnames for local config sources, useful when comicbox is a
      library.

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

- issue\_count type change from decimal to int

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

- Fix parsing and writing genre, story\_arc, series\_groups tags

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
