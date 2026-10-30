# 📰 News

## v5.5.0

### 💥 Breaking Changes

- Metron authenticates only with an API token; username, password and keyring
  support are gone.
- `OnlineCredentials` drops `metron_user` and `metron_password`.
- MetronInfo.xml is written as v1.2 instead of v1.1.

### ✨ Added

- MetronInfo v1.2: series end year, status and summary.

### 🐛 Fixed

- Languages with a region or script, like `pt-BR` or `zh-Hant`, are no longer
  dropped.
- `--cache refresh` no longer breaks another program sharing the Metron cache.
- Corrupt Metron cache files are rebuilt; ones from a newer mokkari are left
  alone.
- Metron honors a `--cache-ttl` under a day, and empty search results expire
  within a day.
- mokkari log messages follow comicbox's log level and format.
- Reading pages from some PDFs no longer hangs or errors.

### 🧑‍💻 Developer

- Requires mokkari 5.0. The Metron cache starts empty on the first run.
- No longer requires keyring.
- PDF support requires comicbox-pdffile 1.1, which uses pymupdf-lite. pip users:
  uninstall pymupdf, then reinstall pymupdf-lite. `comicbox doctor` warns if
  both are installed. If you override the dependency for full pymupdf, comicbox
  will work.

## v5.4.0

### ✨ Added

- Series end year, status and summary in comicbox.json and comicbox.yaml.
- Online tagging fills series years, status, summary and issue count, the
  publication format from Metron, and tags from Comic Vine concepts and objects.
- Match prompts show each candidate's series start year, publisher, issue count,
  issue title and description, and Metron's publication format when titles would
  otherwise read the same.

## v5.3.2

### 🐛 Fixed

- Renamed files no longer contain colons or other characters Windows and SMB
  shares can't store.
- Metron API tokens are used alone: leftover username/password settings no
  longer warn, and `~/.netrc` no longer overrides them.

### 🧑‍💻 Developer

- Requires mokkari 4.10.

## v5.3.1

### 🐛 Fixed

- `OnlineSession` accepts `MatchMode.ASK` when a prompt handler or deferred
  prompts can resolve its prompts, so an embedding app can review every match.

## v5.3.0

### 💥 Breaking Changes

- Requires Python 3.11 or later.

### ✨ Added

- `comicbox doctor` checks archive tools, the PDF extra, image codecs, config,
  credentials and package versions, with a fix for each problem. `--online all`
  also tests each credential with one API request.

### 🐛 Fixed

- CBR support is detected by test-extracting a file; a missing or broken RAR
  tool is reported instead of crashing reads.
- A broken PDF install disables PDFs with a warning instead of breaking
  comicbox, and `is_pdf_supported()` agrees.
- A malformed user config is skipped with a warning, and config errors print one
  line instead of a traceback.
- Per-source online tuning values are validated; unknown sources warn.
- A broken 7z or RAR library no longer aborts batch reads.
- Short-form PDF dates, like those without a timezone, are no longer dropped.
- Filenames with long digit runs no longer stall parsing.
- Config mappings accept enum members like `MatchMode.EAGER` as well as their
  string values.
- Error messages keep bracketed text like `[digital]`.

### 🧑‍💻 Developer

- Requires comicfn2dict 1.0, comicbox-pdffile 1.0, simyan 4.2, mokkari 4.9 and
  packaging. No longer requires imagehash, numpy, scipy or PyWavelets.

## v5.2.2

### 🐛 Fixed

- `get_page_by_index()` returns `None` for an index past the last page instead
  of raising `StopIteration`.
- Extracting covers writes each cover once. A cover found by more than one
  heuristic was written, and counted, once per heuristic.

## v5.2.1

### 🐛 Fixed

- `OnlineSession.close()` releases Comic Vine's connections and sqlite handles
  too, not just Metron's.

## v5.2.0

### ✨ Added

- `comicbox.predict.predict_write_destination()` reports where a write would
  land, and whether that path is taken, before anything is written.
- A destination collision raises `DestinationOccupiedError`, which names the
  occupied path and says which kind of collision it was.
- Match candidates carry a full-size cover url alongside the thumbnail.
- `OnlineSession.close()` releases the pooled Metron connections; the CLI does
  this at the end of every run.

### ♻️ Changed

- Metron requests reuse one pooled connection per run instead of a new TLS
  handshake each (mokkari 4.8.0).

### 🐛 Fixed

- `bulk_write` checks every destination before doing any work, so a batch fails
  fast instead of repacking an archive and refusing it at the end.
  `preflight=False` restores the old behavior.
- Two archives in one batch that convert to the same name now lose
  deterministically, by submission order, instead of by thread race.
- A kept-original CBR whose CBZ twin already exists is refused before its
  metadata is read, on the command line as well as the API.

### 🧑‍💻 Developer

- Requires mokkari 4.8.0. Metron pacing now registers through mokkari's
  `rate_limiter` hook instead of overriding a private method.

## v5.1.2

### ✨ Added

- The end-of-run Metron summary counts connection failures and responses that
  arrived without rate-limit headers.

### ♻️ Changed

- A Metron search that misses now costs 2 API requests instead of up to 6.

## v5.1.1

### ✨ Added

- A run that stops itself says why. `OnlineSession.abort_reason` carries the
  reason a lookup aborted the batch — most usefully a spent daily API quota,
  which stops a run nobody asked to stop. A caller's own `cancel()` leaves it
  unset, so an embedding application can tell a pause it initiated from one the
  server forced.
- A search the daily-quota reserve stopped now reports `Skipped` with
  `reason="quota_reserved"` instead of passing for a source that looked and
  found nothing. Those two call for opposite handling: a comic nobody searched
  for should be tried again tomorrow, and one that genuinely missed should not.
  The matcher's own reason is now the exported constant `SKIP_MATCHER_DECLINED`
  alongside `SKIP_QUOTA_RESERVED`.

## v5.1.0

### ✨ Added

- Comicbox warns when Metron's daily quota drops below 10%, stops starting new
  searches near the floor so the rest of the budget finishes comics that already
  matched, and stops cleanly at zero. Re-running is cheap — the response cache
  replays what was already fetched.
- The end-of-run summary reports API cost: requests sent per endpoint,
  rejections, seconds spent pacing, and the remaining per-minute and daily
  budgets.
- `online.tuning.per_source.metron.rate_limit.per_minute` works again, as a
  ceiling on the server-reported limit. Set it to share one token between
  several processes. Note that a config which already sets it was being warned
  it was ignored, and will now actually be held to it. `per_day` is still
  ignored and still says so.
- `--jobs` is no longer capped at 20 for Metron runs. The cap bounded workers,
  which is not what Metron throttles; the gate bounds requests.
- The outgoing User-Agent identifies the entry point, e.g.
  `comicbox/5.1.0 (cli; jobs=8)`. `OnlineSession(client_name=...)` names an
  embedding application.
- `metron_requests_for_batch(comics, series)` prices a batch the way one
  actually runs — each series resolved once, the rest of its comics at the warm
  price — instead of charging every comic a cold search. Pacing math now prefers
  the burst limit Metron reported over the documented default.

### ♻️ Changed

- A `-j N` batch resolves each series once instead of once per worker. Workers
  that want the same series wait for whoever is resolving it and then take the
  warm path, and the dispatcher hands the pool one file per series first, so its
  first N tasks are N different series rather than N copies of the same cold
  search.
- Metron batches holding many comics from one series fetch that series' issue
  list once instead of once per comic, when Metron's reported issue count says
  that is actually cheaper. A 100-issue single-series run drops from about 200
  requests to about 102.
- Comic Vine tagging spends half the API budget it used to. simyan 4.1.0 stops
  paginating past a short page, so each candidate volume's issue lookup costs
  one request against Comic Vine's 200-per-hour `issues` pool instead of two.
  That pool paces a Comic Vine run, so runs are faster as well as cheaper, and
  `estimate_run()` now projects the request count rather than a floor half its
  size.

### 🐛 Fixed

- A comic with no issue number no longer mis-tags itself with the first issue of
  a series matched earlier in the same run.
- Metron tagging no longer sends requests the server is going to refuse. Every
  request now passes through a process-wide rate gate that models Metron's own
  sliding window, so a `-j N` batch stays inside the per-minute limit instead of
  discovering it by being rejected. This matters more than it sounds: Metron
  counts a rejected request against the daily quota exactly like a successful
  one, so the old behavior spent budget on nothing. Reported as
  [#207](https://github.com/ajslater/comicbox/issues/207).
- A rate-limit rejection now releases one worker when one slot frees, rather
  than every worker at once. `Retry-After` says when a single request becomes
  possible, not when the window refills; waiting it out and then sending the
  whole queue earned one success and a fresh burst of rejections.
- `online.tuning.retry_budget` is wired up. It was parsed, defaulted and then
  never passed to the retry decorator, so a config that set it kept getting the
  built-in 5 attempts; it now gets the number it asked for.
- An aborted lookup is no longer retried. Nothing classified
  `OnlineLookupAbortedError`, so it fell through to the retriable default and
  was replayed on the rate-limit schedule.

### 🧑‍💻 Developer

- Require simyan >= 4.1.0.

## v5.0.0

### 💥 Breaking Changes

- Comicbox schema v3.0. Version 2.0 documents no longer load.
- Credit roles and age ratings use MetronInfo's names and scale, so finer
  ComicInfo ratings like `Everyone 10+` become `Everyone`. The primary credit
  flag is now per role, not per person.
- `manga` no longer carries reading direction. See the new `reading_direction`
  and `manga_volume` fields.
- Web links moved out of `identifiers` into a new `urls` list, and
  `identifier_primary_source` became `primary_id_source`.
- ComicInfo's `GTIN` holds a barcode again instead of a comicbox urn, which is
  what Kavita, Komga and Mylar expect. Files written the old way read.
- A stated `title` is kept as written and stories are only read out of it when
  the comic lists none. A series' other names live in
  `series.alternative_names`.
- Removed `critical_rating` and `alternate_images`, which mapped to no format.
- Removed `--replace`; use `--merge-mode update`. The write API takes
  `merge_mode` instead of `mode`, and `WriteMode` is now `MergeMode`.
- `OnlineSession` takes `match` and `prompts` instead of `mode` and
  `unattended`, matching `--match` and `--prompts`. `set_mode` and
  `set_unattended` are `set_match` and `set_prompts`, the prompt objects carry
  `match` and `prompts`, and the `set_unattended` selector action is
  `set_prompts`, which names the policy it sets and so can turn prompts back on.
- Environment variables nest with `__`, and every config key can be set that
  way: `COMICBOX_ONLINE__AUTH__METRON__KEY`. Old flat names warn.
- `estimate_run()` and `requests_per_comic()` take an `effort` instead of a
  match mode, which never changed what a search costs.

### ✨ Added

- New `--merge-mode` chooses how supplied metadata merges into a comic's
  existing tags: `additive` (the default), `replace` or `update`.
- Web urls in the Notes field are read into `urls`.
- Online API: new `SourceStarted` event, `Effort` is exported alongside
  `MatchMode`, and `rate_limit_status()` now covers Comic Vine as well as
  Metron.
- `OnlineSession` accepts a `config`, the settings it layers its tagging
  preferences over. An embedder that already holds configured settings — naming
  its own cache directory or effort — hands them over instead of exporting
  environment variables for the settings loader to find.

### ♻️ Changed

- A 200 page, 117 MiB CB7 converts in 6.2s instead of 232s, with 318 MiB peak
  RSS instead of 1.9 GiB.
- Online tagging batches by series, downloads covers in parallel and bounds
  Comic Vine calls per comic (`--effort thorough` restores the unbounded
  search). Rate-limit waits are interruptible again.
- Comicbox starts about a third faster and building a `Comicbox` is about forty
  times cheaper. Books with many reprints read up to fifty times faster.

### 🐛 Fixed

- Two silent data losses: an XML tag carrying an attribute, like
  `<Series lang="en">`, took the file's whole metadata down with it, and
  MetronInfo tag-level ids were discarded in files that name no primary id
  source.
- Writing metadata no longer rewrites a comic's pages, so tagging is faster and
  an interrupted write can't damage a page. One archive named twice in a batch
  is no longer repacked by two threads at once and destroyed.
- Online tagging reports a match only when metadata was really applied, and a
  lone mediocre match no longer auto-writes without a prompt. Prompts hold up
  under batch and parallel runs.
- `--effort balanced` is honored; a large unattended run no longer quietly
  downgrades it to `minimal` for Comic Vine.
- `-c/--config` loads the file it names instead of being ignored, and an unknown
  `--online` source is an error rather than a silent widening: a typo like
  `--online metrn` queried every configured database.
- Reading metadata no longer depends on write settings, so
  `--online --write … --rename` no longer names the file from stale data.
- A comic that can't be read no longer ends the batch, and `comicbox` exits
  non-zero whenever any file failed.
- MetronInfo alternative name ids link to their series, and reprint ids to the
  issue they reprint, instead of to pages that don't exist.
- The no-TTY hint names `--prompts never` instead of `--unattended`, which never
  existed.
- Many smaller repairs to credit roles, tag coverage, identifiers, urls and odd
  data that used to cost a whole comic. Metadata comicbox skips is now named in
  a warning instead of dropped silently.

### 🧑‍💻 Developer

- Require simyan >= 4.0.0.

## v4.8.6

### ✨ Added

- `Comicbox.predict_filename()` returns the scheme name `rename_file()` would
  rename to, without renaming. `rename_file()` now uses it, so a caller can show
  or check the destination first.

### 🐛 Fixed

- Renaming keeps the archive's own file extension. The name ends in `ext`, a
  metadata field, so a config that skips it fell back to "cbz" and a stale value
  embedded by another tagger overrode the real one — either way renaming a PDF
  or CBT to a name claiming to be a zip.
- Converting no longer writes the pre-conversion `ext` into the new archive's
  metadata, which is what left those stale values behind.
- Archives differing only by suffix no longer destroy each other when converted
  in one bulk write. They all convert to the same `.cbz`, and the loser could
  replace the winner's finished file while `delete_orig` unlinked both
  originals; it now fails cleanly instead.

## v4.8.5

### ✨ Added

- `write_metadata` and `bulk_write` results report `final_path`: the archive's
  on-disk path after the write. It differs from the submitted `path` when the
  write repacked an unwritable archive (CBR/CBT/CB7) into a CBZ, so callers
  tracking files on disk can follow the conversion.

## v4.8.4

### ✨ Added

- Short options for more common flags. See `--help`.

## v4.8.3

### 🐛 Fixed

- CBR files whose RAR3 extended timestamps carry a sub-second remainder of a
  second or more no longer fail to open with
  `ValueError: microsecond must be in 0..999999`. rarfile <= 4.5 overflows
  parsing these, which some third-party packers write; comicbox now carries the
  excess into whole seconds. The patch deactivates itself if a future rarfile
  fixes the overflow.
- Content based archive detection tries formats in observed frequency order
  (zip, rar, pdf, 7z, tar) when the file extension hint misses, instead of
  trying the rarest formats first. Every detector in that order now requires
  leading magic — zip included — so a pdf or 7z with zip data appended can no
  longer be claimed by the zip tail scan; zips with prepended data
  (self-extractors) are still detected by a terminal loose pass.

## v4.8.2

### ✨ Added

- Metron tagging populates `language` from the issue's series.
- Metron prices in EUR and ITL are attributed to Italy. EUR is deliberate:
  metron.cloud's euro prices currently all come from its Italian comics catalog.

### 🧑‍💻 Developer

- Require mokkari >= 4.5.0.

## v4.8.1

### 🧑‍💻 Developer

- Require simyan >= 3.1.0 and use its new `search_volumes()` API.

## v4.8.0

### ✨ Added

- `OnlineSession` accepts pinned per-source issue `ids`. A source with an id
  fetches it directly while the other enabled sources search, so one session can
  mix id retrieval and search and merge both results.

## v4.7.1

### ✨ Added

- `--auth` takes an API token directly, as `--auth metron:TOKEN` or
  `--auth comicvine:KEY`.
- Metron username and password authentication is deprecated and now warns. It
  will be removed in a future release; generate a token on your metron.cloud
  account page.

## v4.7.0

### ✨ Added

- Metron accepts an API token instead of a username and password. Set it with
  `--auth metron:key=TOKEN`, the `COMICBOX_METRON_KEY` environment variable, or
  the `online.auth.metron.key` config key. The token wins if both are set.

## v4.6.1

### 🐛 Fixed

- Hand-tagged identifier keys with a type prefix, like `series:178012`, now
  produce correct per-database URLs instead of embedding the prefix in an
  issue-shaped URL. Affected every source, notably ComicVine, Metron, Grand
  Comics Database, and League of Comic Geeks.
- Hand-tagged ComicVine long codes like `4050-160294` are normalized to the bare
  id with the right URL.
- `source:type:key` identifier strings in tags no longer drop the id number.
- All URNs in a notes field are read as identifiers; previously only the first
  was.
- Story arcs tagged online from Metron or ComicVine get web URLs.

## v4.6.0

### ✨ Added

- Metron and ComicVine online tagging record a series' alternative names
  (localized and variant titles) as alternate-series reprints, the same way
  MetronInfo.xml's `Series/AlternativeNames` are read. Metron alternative names
  arrive with mokkari 4.3.0; ComicVine's come from volume aliases.
- Online matching recognizes ComicVine volume aliases. A comic filed under a
  localized or variant series title now matches its canonical volume, both in
  candidate scoring and in the pre-call volume filter.

## v4.5.1

### 🐛 Fixed

- ComicInfo.xml's `BlackAndWhite` tag works in both directions. The `Yes` value
  was missing from its enum, so `monochrome` could never be read from a comic
  nor written to one, leaving the field impossible to set or clear. The schema's
  `Unknown` reads as no value.
- Enum tags that accept booleans (`BlackAndWhite`, `Manga`) now handle `False`
  as well as `True`. Writing either previously raised and dropped the tag.

## v4.5.0

### ✨ Added

- The public write API can now clear fields: `write_metadata()` and
  `BulkWriteItem` accept `delete_keys`, glom key paths removed from the final
  metadata before writing (layered onto the config's `general.delete_keys`).
  Empty patch values are pruned on schema load, so previously an update-mode
  write could never clear an existing tag. The patch may be empty when
  `delete_keys` is non-empty (a pure-clear write).
- Extracting a range of PDF pages as PDFs now writes one PDF of the whole range
  instead of a file per page.

### 🐛 Fixed

- Default PDF to CBZ conversion produced an archive of raw `.ppm` pixmaps that
  comic readers (including comicbox itself) do not recognize as pages, yielding
  a zero page book — and `--delete-orig` then removed the working original.
  Conversion now defaults to `pixmap_jpeg` whole-page renders, which also apply
  pdf display rotation.
- `--pdf-pages image` extraction and conversion wrote rotated pages as stored —
  sideways or upside down for scans that rely on `/Rotate` (or a rotated
  content-stream placement) for display. Rotated image-dominant pages are now
  rendered to match the displayed orientation; unrotated pages still extract
  their original bytes untouched.
- Converted pdf pages are now stored uncompressed in the zip like other images;
  the compression decision previously ran before pages gained their image
  suffix, so page images were pointlessly deflated.
- The `--pdf-pages` help lists exactly the values it accepts. It advertised
  `pdf` where unsupported and omitted `image_if_dominant` and `pixmap_jpeg`.
- A PDF with embedded metadata (e.g. a written ComicInfo.xml) no longer counts
  that file as an extra page, which inflated the page count and left a stray
  file when extracting page ranges.
- Extracted PDF pages are named for their contents. Pages extracted as images
  were given a `.pdf` suffix.

## v4.4.0

### ✨ Added

- Support the MetronInfo.xml v1.1 schema: new AlternativeNumber and
  CommunityRating (AverageRating, RatingCount) tags.
- New comicbox `community_rating` field (average\_rating, rating\_count).
  ComicInfo CommunityRating and ComicBookInfo rating now map to it instead of
  `critical_rating`, which remains but no longer maps to any format.
- New comicbox `alternative_issue` field, parsed into name, number and suffix
  parts like `issue`. The Metron API alt\_number now maps to it instead of the
  issue suffix.
- Metron online tagging now fills `community_rating` from the API's
  average\_rating and rating\_count (mokkari 4.2.0).

## v4.3.0

### ✨ Added

- `OnlineSession.rate_limit_status()` is no longer a stub: Metron entries now
  report the account's live rate-limit budget (burst and daily sustained windows
  — limit, remaining, and reset epoch) that mokkari 4 tracks from
  `X-RateLimit-*` response headers. The daily limit varies by Metron
  OpenCollective donor tier, so this is the only place it's discoverable. Comic
  Vine still reports `{}`; simyan exposes no budget to read. Host applications
  (e.g. Codex) can poll this during a batch run to display live budget.

## v4.2.0

### ♻️ Changed

- Custom Metron rate limits (per\_minute/per\_day) in the config are no longer
  supported and will be ignored in favor of the limits Metron reports for your
  account — mokkari 4 reads them from API response headers, so higher
  OpenCollective donor tiers are picked up automatically. You will see a warning
  if you still have them set. These keys are deprecated for every source and
  will be removed in a future release.
- `--jobs` is capped at 20 (Metron's burst limit) when Metron is an active
  credentialed source for the run; the log explains the cap when it engages.

### 🐛 Fixed

- Rate-limited API responses missing a `Retry-After` header now back off on the
  normal schedule instead of retrying immediately.
- Ignored-config warnings (rate-limit overrides, `--api-url` for Metron) now
  print once per run instead of once per file.

## v4.1.1

### ♻️ Changed

- Upgraded Simyan, the ComicVine API library, for more accurate wait-time
  estimates, fewer hangs, and automatic background cleanup of old cached data.
- Custom ComicVine rate limits (per\_second/per\_hour) in the config are no
  longer supported and will be ignored in favor of the official limits. You will
  see a warning if you still have them set.

## v4.1.0

### ✨ Added

- Batch API callers can project the API-request count and duration of an
  online-tag run via `comicbox.online_session.estimate_run()`, so the request
  model lives with the search flow it describes.

## v4.0.5

### ♻️ Changed

- Metron online tagging now identifies an issue in far fewer API requests —
  often one or two instead of dozens — so tagging is faster and more reliable.
  Courtesy of @bpepple. The --effort option no longer applies to Metron due to
  this improved API.

## v4.0.4

### 🐛 Fixed

- Online tagging now searches using embedded metadata (e.g. series name) instead
  of the filename when both are present, so already-tagged comics match more
  accurately.
- Renaming no longer crashes when metadata contains a path separator (e.g. a
  slash in the series or title); the separator becomes `_` in the name.

## v4.0.3

### ✨ Added

- Add Sweet Shop kebab case filename format. Courtesy of @bpepple.

### 🐛 Fixed

- Online cover matching now works for PDFs; the cover page is rasterized before
  perceptual hashing instead of handing raw PDF bytes to the image hasher.
  Courtesy of @bpepple.
- Security release for dependencies.

## v4.0.2

### 🐛 Fixed

- CBR files whose RAR entries carry sub-microsecond timestamps no longer break
  the `ProcessPoolExecutor` worker pool. `rarfile`'s `nsdatetime` is an
  unpicklable `datetime` subclass; its mtime is now coerced to a plain
  `datetime` so results survive transfer back from worker processes.

## v4.0.1

### 🐛 Fixed

- A source's web URL no longer clobbers its authoritative `<ID>`/GTIN identifier
  key on read. Metron/Comic Vine ids now survive a write→read round trip in
  ComicInfo and MetronInfo, so already-tagged comics refresh via their stored id
  instead of falling through to a full online search.
- Metron url parsing no longer captures a trailing slash into the id key
  (`.../issue/123495/` -> `123495`, not `123495/`).
- The `AutoWritten` event now fires for matches resolved by explicit id or
  stored id, so it reports a source for every auto-written comic.

## v4.0.0 - Online Metadata Tagging

### 💥 Breaking Changes

- Removed the ComicTagger (`comictagger.json`) format.
- Reorganized config files into nested groups (`general`, `read`, `write`,
  `convert`, `online`, …). Flat v3 config files must be migrated.
- Dry-run is now `-n` (was `-y`).
- PDFs no longer decode comicbox metadata hidden in the PDF `keywords` field;
  `keywords` now reads as plain tags. Metadata embedded as files inside a PDF
  still reads normally.
- Library API: `Comicbox(...)` no longer accepts a `logger=` argument and never
  reconfigures the host application's logging. Host apps keep their own loguru
  sinks; the CLI configures its own.
- Library API: operational errors derive from
  `comicbox.exceptions.ComicboxError` (`ArchiveError`, `MetadataError`,
  `ExportError`, …) instead of raising bare `ValueError`. Consumers can
  `except ComicboxError`.

### ✨ Added

- Online metadata tagging from Metron and ComicVine with `--online`. Comicbox
  searches by the comic's series, issue, and year, ranks the candidates, breaks
  close calls with cover-image matching, and writes the best match.
    - `--match {ask | careful | auto | eager}` sets how confidently a match is
      written without asking; `--prompts never` turns prompts into skips for
      cron and batch runs.
    - `--id <db>:<id>` tags by an exact upstream id; `--series-id <db>:<id>`
      constrains a search to a known series.
    - Credentials resolve from `--auth`, `COMICBOX_*` environment variables, the
      config file, or the system keyring.
    - Online responses are cached on disk (`--cache`, `--cache-ttl`); `--effort`
      trades API calls for matching accuracy.
- Process many files in parallel with `-j N`, including batch online tagging.
- New public write API: `comicbox.write.write_metadata` and `bulk_write`.

### ♻️ Changed

- Faster archive reads: the 7z and RAR backends load lazily, the page list is
  derived from cached archive state, and that state is released on `close()`.

### 🐛 Fixed

- Normalize ComicBookInfo `rating` to the canonical 0-5 scale.
- Map Metron price currencies to the correct country.
- Harden credentials against accidental leaks into logs.
- `write_metadata()` accepts the root-wrapped dict `to_dict()` returns; passing
  it used to silently write nothing while reporting success.
- Metadata added with `add_metadata()` after a read is no longer ignored.
- `to_dict()` computes pages and page count correctly when one instance dumps
  multiple formats.
- Exported metadata files no longer end with a trailing blank line.

## v3.0.3

### 🐛 Fixed

- Small crashes with metron credits and comicbox with no path

## v3.0.2

### 🧑‍💻 Developer

- Use new comicfn2dict. Parses more comic filename variations.

## v3.0.1

### 🧑‍💻 Developer

- Require new comicbox-pdffile that doesn't corrupt PDF pages. Includes
  image-dominant page detection (`PDFFile.classify_page`,
  `PDFFile.read_image_if_dominant`, `PDFFile.read_full_pixmap_jpeg`) used by
  browser readers to serve scanned-comic PDF pages as plain `<img>`.

## v3.0.0 - Config Dataclass & Parallel Reads

### 💥 Breaking Changes

- get\_config() now returns a ComicboxSettings dataclass, not a Confuse
  AttrDict. Comicbox constructor now accepts this dataclass instead of an
  AttrDict

### ✨ Added

- Add Age Rating conversion function
  comicbox.enums.maps.to\_metron\_age\_rating(value: str | Enum) ->
  MetronAgeRatingEnum | None

### ♻️ Changed

- Reducing startup time for new instances of comicbox.
- General performance improvements for reading metadata from many files.
- Special multiprocessing and async methods
  comicbox.process.iter\_process\_files() and comicbox.process.aread\_metadata()
  for reading large batches of files at once.
- `Comicbox.get_cover_page(skip_metadata=True)` skips metadata parsing for
  callers that just need the first archive image as a thumbnail. Removes
  per-call schema instantiation and Union resolution overhead.

### 🐛 Fixed

- Stop emitting `metron.cloud/{genre,location,reprint,role,story,tag}/...` URLs
  for Metron identifiers — those paths 404 because Metron has no public web
  pages for those types (only API endpoints). The numeric Metron ID is still
  preserved on the identifier.
- Security against suspicious archive paths when extracting pages and metadata
  to the filesystem.

## v2.2.3

### 🧑‍💻 Developer

- Update marshmallow & rich

## v2.2.2

### 🧑‍💻 Developer

- Update deepdiff library

## v2.2.1

### 🐛 Fixed

- Fix reading PDF metadata breaking on datetimes.
- PDF datetime parsing failures are warned about instead of raising an exception
  and abandoning parsing.

## v2.2.0

### ✨ Added

- Add `--pdf-page-format` option to choose how pdf pages are extracted. Replaces
  `to_pixmap` in the API.
- `--cbz` now works on PDF files. Can create original image CBZs with
  `--pdf-page_format image` for PDFs with single image pages.
- `--validate` validates imported and archive metadata against available schemas
- `--import` expands quoted "glob\*" paths.

### 🐛 Fixed

- Fix comicbox jsonschema.

### 🧑‍💻 Developer

- Many more type annotations. Include py.typed sentinel file.

## v2.1.1

### ✨ Added

- YAML formats now dump unquoted date and datetimes.

### 🧑‍💻 Developer

- Pin confuse config library at 2.1.0 due to typing issues with 2.2.0

## v2.1.0

### ✨ Added

- PDFs now write to pdf embedded files instead of overloading the metadata
  keywords field. Thanks for the idea from @bpepple
    - PDFS still read full metadata formats from the keywords field if they
      exist for backward compatibility.
- Read more flexible datetimes from PDFs

## v2.0.6

### 🧑‍💻 Developer

- Python 3.14 support.

## v2.0.5

### 🐛 Fixed

- A crash when dumping comicbox.json format with only one page.

## v2.0.4

### 🧑‍💻 Developer

- The confuse library dependency doesn't support Python 3.14. So neither does
  comicbox :(

## v2.0.3

### ✨ Added

- Normalize more original\_format names.

### 🐛 Fixed

- ComicInfo.xml coercing Age Rating to wrong value.

### 🧑‍💻 Developer

- Update xmltodict. Removes much comicbox fix code.

## v2.0.2

### ✨ Added

- More aliases for comicvine identifier source.
- Make archive comments that aren't ComicBookInfo JSON log as debug comments
  more often.

### 🐛 Fixed

- Ensure mtimes from archives are timezone aware.

## v2.0.1

### 🐛 Fixed

- Resolve circular import if not installed with \[pdf] option.

## v2.0.0

### 💥 Breaking Changes

- Schema, API, config and CLI changes. See
  [the 2.0 CHANGES document](CHANGES-2.0.0.md).

### ✨ Added

- File Formats
    - CB7 archive read support. Comic archives in 7zip archives.
- Schemas
    - Support the MetronInfo.xml v1.0 Schema
    - Add AniList, Kitsu, MangaDex, MangaUpdates, MyAnimeList identifier
      sources.
    - ComicInfo.xml gains the `Translator` tag
    - PDF `modDate` is now read and written.
    - URNs as serialized identifiers in `notes` tag gain an optional tag type
      attribute in the nss: e.g. `urn:comicvine:series:1234`
    - Comictagger schema supports series\_aliases and title\_aliases as reprints
    - Parse PDF datetime format.
    - Many enum fields now accept caseless and slightly fuzzy value lookups that
      are coerced to correct types for the specified output metadata format.
    - For convenience, named or numbered types or collections in the comicbox
      schema may also be parse by their simple name instead of requiring a
      complex object.
- Config
    - `--delete action` becomes `--delete-all-tags`.
    - `--compute-pages` is off by default. Turn on to recompute ComicInfo style
      `Pages` structures
    - `--no-compute-page-count` prevents recomputing page\_count.
    - `--delete_keys` now excludes keys from loading entirely.
    - Syntax highlighting used on output. Change or remove with `--theme`
      option.

### 🐛 Fixed

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

### 🐛 Fixed

- Story arc parsing.

## v1.2.2

### ♻️ Changed

- Simplify Identifier URL construction for Metron pk ids.

### 🐛 Fixed

- Fix Notes parsing for Comictagger beta Metron origin

## v1.2.1

### ✨ Added

- Detect .jxl extension (JPEG XL) as a comic page.

### 🐛 Fixed

- Fix ignoring MacOS resource forks in archives.
- xml parsing fixes and

### 🧑‍💻 Developer

- Better Python 3.13 support.

## v1.2.0

### ✨ Added

- Add -R --replace\_metadata option. Default behavior is to merge keys.
- Add -D --delete\_keys option.
- Faster metadata writing. Replace files in zipfiles instead of rewriting the
  entire archive.

## v1.1.10

### ✨ Added

- Log common non-ComicBookInfo archive comments with less alarm.

### 🐛 Fixed

- Fix parsing negative issue numbers in filenames.

## v1.1.9

## v1.1.8

### 🧑‍💻 Developer

- Update pycountry

## v1.1.7

### 🐛 Fixed

- Unknown urls give the path, query and fragment as the nss, not the domain

## v1.1.6

### 🐛 Fixed

- Ignore dotfiles and macOS resource forks when finding pages.

## v1.1.5

### 🐛 Fixed

- Fix export of CIX CoverArtist tag.
- Fix tagging Web and other unknown url tags. Accept any url for comicbox
  identifiers.

## v1.1.4

### 🐛 Fixed

- Make language and country code parsing more durable

## v1.1.3

### 🐛 Fixed

- Updated comicfn2dict fixes filename parsing bugs.

## v1.1.2

### 🐛 Fixed

- Fix crash copying directories between archives.
- Fix crash with leftover temp files.

## v1.1.1

### ♻️ Changed

- Write MetronInfo.xml & CoMet.xml in TitleCase for beauty.

### 🐛 Fixed

- Write ComicInfo.xml in TitleCase so Comictagger can find it.
- Fix duplicate reprints.

## v1.1.0

### ✨ Added

- PDFs read all metadata formats from the keywords field.
- PDFs write ComicInfo.xml to keywords field.
- ComicInfo.xml accepts spaces as web field separator.
- Accept numeric types for issues.
- Major improvements to filename parsing and diversity of filename schemas.

### 🐛 Fixed

- Fix `--import` option crash.
- Fix parsing tagger and updated\_at from notes.

## v1.0.0

### 💥 Breaking Changes

- Some are detailed in [The 1.0.0 CHANGES document](CHANGES-1.0.0.md)

### ✨ Added

- Comicbox continues to primarily be an API for reading comic metadata but this
  version contains an enhanced CLI, and more powerful reading, writing,
  synthesis and exporting of metadata.
- Comicbox now sorts archive filenames case insensitively.
- Comicbox now writes identifiers to the notes field in urn format.
- You should probably read the code in `comicbox.box` for public facing apis.

### ♻️ Changed

- comicbfn2dict and comicbox-pdffile are now independent packages.

## v0.10.2

### ✨ Added

- Sophisticated cli metadata parsing. See cli help and README.
    - config.metadata\_cli holds the new string format.
- Writing xml and json metadata to files is now pretty printed.

### 🐛 Fixed

- Fix some instances where falsey values were not written.
- Fix comicinfo.xml ComicPageInfo typing.

## v0.10.1

### ♻️ Changed

- Change --metadata cli syntax to use key=\[a,b,c] for arrays and key=a for
  simple values.

## v0.10.0

### 💥 Breaking Changes

- Breaking API, CLI & Config changes.

### ✨ Added

- Write metadata from the command line.
- Optional PDF support. Install as `comicbox[pdf]`
- Extract a range of pages from the cli.

### 🧑‍💻 Developer

- Python version now >=3.9

## v0.9.1

### 🧑‍💻 Developer

- Removed dependence on Python 3.11

## v0.9.0

### ✨ Added

- StoryArc & StoryArcNumber for ComicInfo.xml exported as `story_arcs` dict.
  Supports Mylar multiple story arcs csv values format.

## v0.8.0

### ✨ Added

- Add close\_fd & check\_unrar config options for API use.
- Add ComicArchive.check\_unrar\_executable() public method.

### 🔥 Removed

- Remove closefd constructor option.

## v0.7.1

### ✨ Added

- Test for unrar executable for clearer errors.

### 🔥 Removed

- Remove unrar.cffi support.

## v0.7.0

### ✨ Added

- ComicInfo.xml StoryArcNumber, Review and GTIN now parsed.
- ComicInfo.xml Pages attributes now exposed as snake case for python

### 🐛 Fixed

- Tags from ComicInfo.xml were not parsed

## v0.6.7

### 🐛 Fixed

- Remove unrar-cffi dependency aciddentally left in during testing

## v0.6.6

### ✨ Added

- Print filetype cli option. get\_archive\_type() api method.
- Use unrar.cffi if it's available.

### 🧑‍💻 Developer

- Use importlib instead of deprecated pkg\_resources.

## v0.6.5

### ✨ Added

- Demote parser errors to warnings.

## v0.6.4

### ✨ Added

- --delete-rar option is now --delete-orig

### 🐛 Fixed

- Fix --delete-rar option sometimes deleting original cbzs

## v0.6.3

### 🐛 Fixed

- Fix rename function renaming files to nothing.
- Fix --dry-run feature for rename.

## v0.6.2

### 🐛 Fixed

- Enable support for Deflate64.

## v0.6.1

### 🐛 Fixed

- Fix encoding/decoding crash by replacing uncodable utf-8 characters.

## v0.6.0

### ✨ Added

- Add --metadata cli action. Injects metadata from cli.
- Warn when no actions performed.
- \== operator for metadata is deep and ignores key order.
- Credits are now sorted.

### 🐛 Fixed

- Log format conversions.
- Don't add empty credits list metadata.

## v0.5.5

### 🐛 Fixed

- Fix dest-path cli argument.
- Use defusedxml for XML parsing.
- Fix recursion crash.
- Log exception during recursion and proceed.

## v0.5.4

### 🐛 Fixed

- Remove uneccissary dependencies

## v0.5.3

### 🐛 Fixed

- Fix filename extension parsing
- Renamed underscore cli options to use dash instead
- Fixed crash when recompressing directories.

## v0.5.2

### ✨ Added

- ComicArchive class now has a context manager
- Removed as\_pil() methods for pages and covers

## v0.5.1

### ✨ Added

- Methods for getting covers and pages as PIL Images.
- Lazy metadata and cover pulling. Removes `metadata` and `cover` options.
- closefd option leaves archive open after method calls. Close manually with
  close().
- .cbt Tarfile comic archive support.

## v0.5.0

### ✨ Added

- Issues numbers are now strings.
- Separate read metadata option from print metadata action.
- Added dry\_run option.
- Namespace config under "comicbox" map to allow inclusion in caller configs.
- Allow modnames for local config sources, useful when comicbox is a library.

### 🐛 Fixed

- Trap errors reading user config files.
- Fixed cover extraction to a directory.
- Abort with message if pages asked to extracted to a filee.
- Handle more filename patterns.

## v0.4.1 - Yanked

## v0.4.0

### ✨ Added

- Accept environment variables and config files to configure.
- CLI accepts more than one path as targets for action.
- CLI runs _every_ action on the command line.
- API `get_cover` init variable now set in config as `cover`
- Optional metadata parsing with config.

### 🐛 Fixed

- Fixed some file name patterns

## v0.3.4

### ✨ Added

- More info in parsing warnings.
- More explicit raw tag titles.

### 🐛 Fixed

- Fixed combining CBI credits and with other format credits.

## v0.3.3

### ✨ Added

- add colored python logging

## v0.3.2

### ♻️ Changed

- issue_count type change from decimal to int

## v0.3.1

### ✨ Added

- Extract decimals from strings for more liberal reading.

### 🐛 Fixed

- Fix synthesizing CBI & CIX credits data.

## v0.3.0

### ✨ Added

- CIX gained the `community_rating` attribute from CIX 2.0 spec.
- `age_rating` replaces `maturity_rating` to standardize more on CIX
- `CoverArtist` replaces `Cover` to standardize more on CIX
- Better CIX `Manga` parsing
- Better CIX `BlackAndWhite` parsing
- Added CIX `AgeRating` valid schema values, unused.
- LGPL 3.0

### ♻️ Changed

- CBI changed `critical_rating` to decimal type from string (in CBI it's an
  int).

## v0.2.2

### 🧑‍💻 Developer

- Update pycountry to be compatible with codex

## v0.2.1

### 🐛 Fixed

- Comicbox now raises a specific UnsupportedArchiveTypeError for bad archives

## v0.2.0

### ✨ Added

- Option for getting the cover image at metadata load time as well.

## v0.1.7

### ♻️ Changed

- Remove regex dependency in favor of re module

## v0.1.6

### 🐛 Fixed

- Fixed recursive mode trying to operate on directories
- Fix recompressing crash on cbr -> cbz conversion
- Fixed parsing for three new filename patterns

## v0.1.5

### 🐛 Fixed

- Fix parsing and writing genre, story\_arc, series\_groups tags

## v0.1.4

### 🐛 Fixed

- Make metadata read more robust by catching individual tag exceptions and
  printing them to stdout
- Protect against null people names for credits
- More robust xml volume parsing

## v0.1.3

### 🐛 Fixed

- Fix cli crash with bad import

## v0.1.2

### ✨ Added

- Improve 1/2 Issue number parsing

### 🐛 Fixed

- Fix relative imports
- Fix credit parsing errors

## v0.1.1

### 🐛 Fixed

- Don't crash import on bad credits

## v0.1.0

### ✨ Added

- Initial release
