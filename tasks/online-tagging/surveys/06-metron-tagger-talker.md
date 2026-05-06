# Metron-Tagger `talker.py` — survey

Source:
[`metrontagger/talker.py`](https://github.com/Metron-Project/metron-tagger/blob/main/metrontagger/talker.py).
Line numbers below are approximate (file is ~1100 lines).

## What `Talker` owns

[`Talker.__init__`](https://github.com/Metron-Project/metron-tagger/blob/main/metrontagger/talker.py#L556)
takes `(username, password, metron_info, comic_info)` and wires up:

- `self.api = mokkari.api(username, password, user_agent=f"Metron-Tagger/{__version__}")`
- `self.metron_info` / `self.comic_info` — output format flags from `-m` / `-c`
- `self.match_results = OnlineMatchResults()` — accumulator for ambiguous files
  to revisit at the end
- helper objects: `MetadataExtractor`, `CoverHashMatcher`, `MetadataMapper`,
  `UIPresenter` (the UI/terminal layer wrapping `questionary`)

It does not own the file list, which is passed in per call.

## Top-level identification flow

[`identify_comics()`](https://github.com/Metron-Project/metron-tagger/blob/main/metrontagger/talker.py#L1038)
is the entry point. Per file:

1. Build `ProcessingConfig` from CLI args (`accept_only`, `skip_multiple`,
   `series_id`, `ignore_existing`).
2. Call `_process_file()`:
    1. Open as `Comic`, validate.
    2. `_get_existing_metadata_id()` — if archive carries an embedded Metron ID
       (from a prior tag), use it directly.
    3. Otherwise `_search_by_filename()`.
3. On a resolved id, `_write_issue_md()` fetches and writes the full issue.
4. After the batch, `_post_process_matches()` revisits anything queued as
   "multiple matches" for interactive resolution.

## Search step

[`_search_by_filename`](https://github.com/Metron-Project/metron-tagger/blob/main/metrontagger/talker.py#L854)
parses the filename with `comicfn2dict` to extract series name, issue number,
and year. It composes a `params` dict (series name, issue number, optionally
`year`) and calls `self.api.issues_list(params=params)`.

If `ProcessingConfig.series_id` is set (from `--id`), that id is injected:
`metadata["series_id"] = str(config.series_id)`, restricting the search to
issues of that one Metron series.

## Disambiguation — `CoverHashMatcher`

Defined around
[line 323](https://github.com/Metron-Project/metron-tagger/blob/main/metrontagger/talker.py#L323).
Cover-image based filter for ambiguous results.

- Algorithm: **perceptual hash (pHash)** via `imagehash.phash` on PIL Images.
- Cover bytes come from `comic.get_page(0)` (first interior page is treated as
  the cover); pHash is `lru_cache`-memoized per `Comic` object.
- Threshold: class constant `HAMMING_DISTANCE = 10` — two hashes within ten bits
  are a match.
- Each Metron `BaseIssue` carries a precomputed `cover_hash` string from the
  API, so the local hash is compared against that — no extra image download.
- Surface methods:
    - `is_within_hamming_distance(comic, metron_hash) -> bool`
    - `filter_by_hamming_distance(comic, issues) -> list[BaseIssue]`

## Interactive prompt

When a multi-match cannot be resolved by cover hash and isn't being skipped,
[`_select_choice_from_matches`](https://github.com/Metron-Project/metron-tagger/blob/main/metrontagger/talker.py#L804)
runs:

1. `UIPresenter.print_multiple_match_prompt(filename)` prints the filename
   header.
2. Matches are sorted by `cover_date`.
3. `_create_choice_list` formats each as a one-line summary (publisher / series
   (vol, year) / issue # / cover date).
4. `questionary.select("Select an issue to match", choices=...)` shows a
   keyboard-navigated picker plus a "skip" sentinel.
5. Returns the chosen `issue_id` or `None`.

## Auto-accept logic

Tied to flags from
[`metron-tagger-cli-help.txt`](file:///Users/aj/Test/metron-tagger-cli-help.txt):

- `--accept-only`: `_handle_single_match()` accepts a lone search hit
  immediately, **skipping cover-hash verification**. Multi-match files are still
  queued for prompting.
- `--skip-multiple`: when more than one candidate remains after the cover-hash
  filter, the file is dropped from `multiple_matches` instead of being added to
  the prompt queue — no user interaction.
- Default (neither flag): single matches still go through cover-hash
  verification; multi-matches are prompted.

The two flags are independent and both end up as fields on `ProcessingConfig`
(lines ~54–63).

## ID-only path

`--id ID` populates `ProcessingConfig.series_id`. It does **not** by itself
short-circuit identification — search still runs, but it's constrained to that
Metron series id, narrowing results dramatically. (Direct issue-id override is
reached when the file already carries a Metron issue id from a prior tag —
handled by `_get_existing_metadata_id()`, not by `--id`.)

## Result write-back

[`_write_issue_md`](https://github.com/Metron-Project/metron-tagger/blob/main/metrontagger/talker.py#L1000):

1. `self.api.issue(issue_id)` — fetch the full mokkari `Issue`.
2. `MetadataMapper.map_response_to_metadata(issue)` — convert the mokkari
   pydantic model into the tagger's internal `Metadata` object.
3. `_write_metadata_formats()` — depending on `self.metron_info` /
   `self.comic_info`, serialize and embed `MetronInfo.xml` and/or
   `ComicInfo.xml` into the archive (writing happens through `darkseid`'s
   `Comic` archive helpers).
4. Print success.

The archive itself is mutated in place; no rename/move is done here (rename is a
separate `-r` step).
