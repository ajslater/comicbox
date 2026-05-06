# Comictagger `IssueIdentifier` Digest

Source: `comictaggerlib/issueidentifier.py` (master, 722 lines), companion
`comictaggerlib/imagehasher.py`. Note: this is the legacy Python 2-style
identifier still on master; the codebase has since been refactored, but the
algorithm is the canonical reference.

## Class & top-level flow

`IssueIdentifier` ([issueidentifier.py#L51](https://github.com/comictagger/comictagger/blob/master/comictaggerlib/issueidentifier.py#L51))
owns the `comic_archive`, `settings`, hasher selection, hamming thresholds, and
a result enum (`ResultNoMatches`, `ResultOneGoodMatch`, `ResultMultipleGoodMatches`,
`ResultMultipleMatchesWithBadImageScores`, `ResultFoundMatchButBadCoverScore`,
`ResultFoundMatchButNotFirstPage` — [#L53-L58](https://github.com/comictagger/comictagger/blob/master/comictaggerlib/issueidentifier.py#L53)).

Entry point is `search()` ([#L298](https://github.com/comictagger/comictagger/blob/master/comictaggerlib/issueidentifier.py#L298)):

1. Pull cover hash from page 0 (`cover_page_index`) ([#L313](https://github.com/comictagger/comictagger/blob/master/comictaggerlib/issueidentifier.py#L313)).
2. If aspect ratio < 1.0 (wider than tall = 2-page spread), crop right half and hash that too as `narrow_cover_hash` ([#L320-L325](https://github.com/comictagger/comictagger/blob/master/comictaggerlib/issueidentifier.py#L320)).
3. Build search keys from `additional_metadata` > internal CIX/CBI > filename ([#L156](https://github.com/comictagger/comictagger/blob/master/comictaggerlib/issueidentifier.py#L156)).
4. ComicVine `searchForSeries` → filter by length-delta, publisher blacklist, future start year ([#L379-L412](https://github.com/comictagger/comictagger/blob/master/comictaggerlib/issueidentifier.py#L379)).
5. `fetchIssuesByVolumeIssueNumAndYear` → shortlist of (series, issue) pairs.
6. For each shortlist item, `getIssueCoverMatchScore` against CV primary cover ([#L506-L539](https://github.com/comictagger/comictagger/blob/master/comictaggerlib/issueidentifier.py#L506)).
7. If best score is poor, second pass with archive pages 1-2 + remote alternate covers ([#L596-L658](https://github.com/comictagger/comictagger/blob/master/comictaggerlib/issueidentifier.py#L596)).
8. Prune any match more than `min_score_distance` worse than best ([#L666-L668](https://github.com/comictagger/comictagger/blob/master/comictaggerlib/issueidentifier.py#L666)).
9. Drop CV volumes with `count_of_issues == 1` if local `issue_count != 1` (TPB-vs-limited tiebreaker, [#L673-L685](https://github.com/comictagger/comictagger/blob/master/comictaggerlib/issueidentifier.py#L673)).

## Hash algorithm

`ImageHasher` ([imagehasher.py#L29](https://github.com/comictagger/comictagger/blob/master/comictaggerlib/imagehasher.py#L29)) uses **PIL only** (no `imagehash` lib). `calculateHash()` ([issueidentifier.py#L116](https://github.com/comictagger/comictagger/blob/master/comictaggerlib/issueidentifier.py#L116)) dispatches by `image_hasher`:

- `'1'` (default) → `average_hash()` — **aHash**, 8x8 grayscale, mean threshold, 64-bit int ([imagehasher.py#L46](https://github.com/comictagger/comictagger/blob/master/comictaggerlib/imagehasher.py#L46)).
- `'2'` → `average_hash2()` — Laplacian convolve (stub, commented out).
- `'3'` → `dct_average_hash()` — pHash 32x32 DCT (stub, commented out).

So in practice it's **aHash, 8x8 = 64 bits**. Distance is plain Hamming via `ImageHasher.hamming_distance`.

## Source vs candidate covers

- **Source:** `ca.getPage(self.cover_page_index)` — page 0 by default ([#L313](https://github.com/comictagger/comictagger/blob/master/comictaggerlib/issueidentifier.py#L313)). On weak first-pass scores, pages 1-2 are added ([#L605-L608](https://github.com/comictagger/comictagger/blob/master/comictaggerlib/issueidentifier.py#L605)).
- **Candidate:** ComicVine `issue['image']['thumb_url']` fetched fresh per call via `ImageFetcher().fetch(..., blocking=True)` ([#L222](https://github.com/comictagger/comictagger/blob/master/comictaggerlib/issueidentifier.py#L222)) — uses thumb (not super) for hashing; primary URL is recorded for the result.

## Thresholds (hamming distance, lower=better)

Set in `__init__` ([#L66-L83](https://github.com/comictagger/comictagger/blob/master/comictaggerlib/issueidentifier.py#L66)):

| name | value | meaning |
| --- | --- | --- |
| `strong_score_thresh` | 8 | early-exit "definitely this one" |
| `min_alternate_score_thresh` | 12 | required when matching alt covers/inner pages |
| `min_score_thresh` | 16 | best > this triggers second-pass alt-cover analysis |
| `min_score_distance` | 4 | gap from best required to drop a candidate |

## Scoring

Pure hamming, **no weighted blend with metadata signals**. Series similarity, year, issue# act as **filters before hashing**, not score components. After hashing, the only post-hoc tweak is the count-of-issues TPB filter ([#L673](https://github.com/comictagger/comictagger/blob/master/comictaggerlib/issueidentifier.py#L673)).

`getIssueCoverMatchScore` scores `localCoverHashList` (cover + optional narrow-crop + optional pages 1-2) against `remote_cover_list` (CV primary + optional alts), returns `min(score)` ([#L290](https://github.com/comictagger/comictagger/blob/master/comictaggerlib/issueidentifier.py#L290)). Hits `strong_score_thresh` → early break.

## Variants

Round 1 hashes only the primary cover. If best score >= `min_score_thresh`, round 2 calls `comicVine.fetchAlternateCoverURLs(issue_id, page_url)` and hashes each ([#L243-L260](https://github.com/comictagger/comictagger/blob/master/comictaggerlib/issueidentifier.py#L243)). A candidate survives only if its best alt-cover score < `min_alternate_score_thresh` (12).

## When is hashing used?

**Always**, from the start. Hashing is the primary discriminator across every shortlist member, run sequentially per candidate. There's no count-based gate — even a single shortlist item is hashed and can return `ResultFoundMatchButBadCoverScore` if the score is weak.

## Result classification

After pruning ([#L687-L713](https://github.com/comictagger/comictagger/blob/master/comictaggerlib/issueidentifier.py#L687)): `len==1` → `ResultOneGoodMatch`; `len==0` → `ResultNoMatches`; `len>1` → `ResultMultipleGoodMatches`. The earlier weak-score branch yields `ResultFoundMatchButBadCoverScore` (single survivor) or `ResultMultipleMatchesWithBadImageScores`.
