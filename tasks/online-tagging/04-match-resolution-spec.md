# Phase 4 — Match Resolution Spec

Defines how comicbox turns a list of API search results into a single accepted
match per online source, given a comic with imperfect existing metadata.
Plugs into the `OnlineMatcher` integration point declared in
[03-architecture-spec.md](03-architecture-spec.md).

## Decisions confirmed

From earlier phases:

- Cover hash: pHash via `imagehash`, 64-bit, Hamming threshold 10. Distance is
  blended into a unified confidence score, not used as a hard filter.
- Match Resolution Policy: default prompt; `--accept-only` and
  `--skip-multiple` compose orthogonally; both = unattended.
- The `OnlineMatcher` is invoked from `ComicboxOnlineLookup` (between Normalize
  and Merge) per active source per comic.

## Pipeline integration

```
For each comic:
    For each active OnlineSource (in merge_order):
        1. Build SearchCriteria from normalized comic profile.
        2. candidates = source.search(criteria)         # 10–20 items typical
        3. matcher.rank(candidates, comic) → [(c, score), …]   # sorted desc
        4. resolution = policy.apply(ranked, settings)
              → AUTO_WRITE(c) | PROMPT(ranked) | SKIP | NO_MATCH
        5. If PROMPT: selector_callback(ranked, ctx) → index | None
        6. If a candidate is chosen: source.get(candidate.issue_id) → full
           record; transform; add_source().
```

Each source resolves independently. A comic can produce a Metron match and a
ComicVine match in the same run; both sources' data merges per `merge_order`.

## Comic profile (input to the matcher)

Built from the post-normalize, pre-online merged metadata. Just enough fields
to score candidates against:

```python
@dataclass(frozen=True, slots=True)
class ComicProfile:
    series: str | None              # series name
    issue: str | None               # issue number as string ("1", "1.5", "0", "0a")
    issue_int: int | None           # parsed integer for fast equality, None if non-numeric
    year: int | None                # publication year, parsed from cover_date
    publisher: str | None
    page_count: int | None
    cover_bytes_provider: Callable[[], bytes]   # lazy; only called if hashing needed
```

`ComicProfile` is constructed once per comic; reused across sources.

## Candidate (matcher output unit)

```python
@dataclass(frozen=True, slots=True)
class Candidate:
    source: str                      # "metron" | "comicvine"
    issue_id: int                    # source-native id
    summary: CandidateSummary        # display fields
    raw: Mapping[str, Any]           # native API response, untransformed
    metadata_score: float            # [0,1] from non-hash signals
    cover_score: float | None        # [0,1] hash-derived, or None if not hashed
    score: float                     # final [0,1] blend
    url: str                         # source-built canonical URL for "open in browser"

@dataclass(frozen=True, slots=True)
class CandidateSummary:
    series: str
    issue: str
    year: int | None
    publisher: str | None
    page_count: int | None
    cover_url: str | None
    variant_label: str | None
```

## Signals

Each signal returns a value in `[0, 1]`. Missing inputs are treated as
specified; the goal is "missing info shouldn't penalize harder than wrong info."

| Signal | Computation | Weight |
|---|---|---|
| **Series similarity** `s_series` | `rapidfuzz.fuzz.WRatio(normalize(profile.series), normalize(candidate.series)) / 100`. Normalization: lowercase, strip volume suffixes (`(vol. N)`, `vol. N`, `volume N`), collapse non-alphanumeric whitespace, deduplicate spaces. Returns 0 if either side missing. | 0.30 |
| **Issue match** `s_issue` | If both `issue_int` populated: `1.0 if equal else 0.0`. If both string-equal (case-insensitive): `1.0`. Else 0. Variant suffixes (`1a`, `1b`) compared as full strings. Missing on either side: `0.5` (uncertain). | 0.25 |
| **Year match** `s_year` | `1.0` if `\|profile.year - candidate.year\| == 0`, `0.7` if ±1 (cover-date vs publication-year drift), `0.4` if ±2, else `0`. Missing on either side: `0.6`. | 0.10 |
| **Publisher match** `s_publisher` | Normalize (lowercase, strip "Inc", "Comics" suffixes for resilience), `1.0` if equal, `0.5` if missing, else `0`. | 0.10 |
| **Page count match** `s_pages` | `1.0` if equal, `0.7` if within 10% (handles ads/no-ads variants), `0.3` if within 25%, else `0`. Missing on either side: `0.6`. | 0.05 |
| **Cover hash similarity** `s_cover` | `1 - (hamming_distance / 64)`. Only computed when invoked (see policy). When invoked but hash unavailable for this candidate (no cover URL): `s_cover = None`. | 0.20 (when computed) |

The metadata-only weights (`w_series + w_issue + w_year + w_publisher +
w_pages = 0.80`) reserve `0.20` for the cover-hash signal.

## Score formula

Two passes. The matcher computes `metadata_score` for every candidate, then
optionally invokes cover hashing.

```python
def metadata_score(c: Candidate, p: ComicProfile) -> float:
    components = {
        s_series(p, c)     * 0.30,
        s_issue(p, c)      * 0.25,
        s_year(p, c)       * 0.10,
        s_publisher(p, c)  * 0.10,
        s_pages(p, c)      * 0.05,
    }
    return sum(components) / 0.80   # renormalize to [0,1]

def final_score(c: Candidate, p: ComicProfile, hash_used: bool) -> float:
    if not hash_used or c.cover_score is None:
        return c.metadata_score
    return 0.80 * c.metadata_score + 0.20 * c.cover_score
```

Mixing hashed and unhashed candidates in the same ranking is fine: the hashed
candidates have a slightly different score scale, but the `0.20` weight is
small enough that ordering by `final_score` remains correct in practice.

## Cover-hash invocation policy

Hashing is precision-optimised disambiguation, not a primary signal. Trigger
rules, evaluated against the metadata-only ranking:

1. **Skip hashing entirely** when the top metadata_score ≥
   `confidence_threshold` AND the gap to second is ≥ `disambiguation_margin`
   (default `0.10`). The match is unambiguous on metadata alone.
2. **Hash the top K candidates** (default `K=5`) when:
   - top.metadata_score is between `min_confidence` and `confidence_threshold`
     (uncertain), OR
   - multiple candidates exceed `min_confidence` and the gap between top and
     second is < `disambiguation_margin` (close-call).
3. **Skip hashing** when no candidate exceeds `min_confidence`. The match is
   doomed regardless of hash.

For Metron candidates, hashing is free: mokkari returns a precomputed
`cover_hash` string (server-side pHash). Comicbox computes the local cover's
pHash once per comic (cached on the `ComicboxComputed` layer). Hamming
distance is a string XOR-popcount.

For ComicVine (and future GCD) candidates, hashing requires downloading the
candidate cover thumbnail. Cover URLs are cached separately from the response
cache (`${cache_dir}/cover_hashes.sqlite`, key = URL → pHash) so re-runs avoid
re-downloading.

The local comic's cover bytes are obtained via
[`get_cover_page(skip_metadata=True)`](../../comicbox/box/pages/covers.py:86) —
no PIL conversion in core; PIL/imagehash is only loaded when `cover_bytes_provider()`
is actually called.

## Default thresholds

| Setting | Default | Role |
|---|---|---|
| `confidence_threshold` | `0.85` | Auto-write boundary. Matches at or above this write without prompt (when policy permits). |
| `min_confidence` | `0.50` | Drop threshold. Candidates below this never propose; logged at INFO. |
| `disambiguation_margin` | `0.10` | Top vs runner-up gap below which hashing is forced. Not user-exposed initially. |
| `top_k_for_hashing` | `5` | How many top candidates get hashed when triggered. Not user-exposed initially. |

These are placeholders. Calibration approach:

1. Curate ~100 fixture comics with manually-verified Metron and CV ids.
2. Run the matcher; record `metadata_score` and (if invoked) `final_score`
   for the *correct* match per comic.
3. Pick `confidence_threshold` such that ≥95% of correct matches clear it
   without false-positives from runners-up.
4. Pick `min_confidence` such that ≥99% of correct matches stay above it AND
   the bulk of wrong-issue candidates fall below it.
5. Re-run on a held-out set; iterate.

Calibration tooling (a small CLI `comicbox _matcher_eval <fixture_dir>`) is
implementation work in the matcher milestone; spec it then.

## Match Resolution Policy outcomes

After ranking and applying invocations, the matcher emits a `Resolution`:

```python
@dataclass
class Resolution:
    kind: Literal["AUTO_WRITE", "PROMPT", "SKIP", "NO_MATCH"]
    chosen: Candidate | None
    candidates: tuple[Candidate, ...]   # sorted desc by score
```

Decision tree, given the policy flags:

```
if no candidate ≥ min_confidence:
    NO_MATCH
elif top.score ≥ confidence_threshold and gap ≥ disambiguation_margin:
    AUTO_WRITE(top)
elif --accept-only and exactly one candidate ≥ min_confidence:
    AUTO_WRITE(that one)        # accepted below threshold per Phase 2 semantics
elif --skip-multiple and >1 candidates ≥ min_confidence:
    SKIP                        # log "ambiguous, skipped"
else:
    PROMPT(candidates)
```

`AUTO_WRITE` and the chosen-via-prompt branch both end with `source.get(c.issue_id)`
followed by transform + `add_source()`.

`NO_MATCH`, `SKIP`, and a user-rejected `PROMPT` all leave the comic
unchanged for that source. Other sources still try.

`NO_MATCH` under `--accept-only` is logged at INFO per the Phase 2 resolution
("zero candidates clear `min_confidence` → log the miss").

## CLI prompt UX

Triggered by `Resolution.kind == "PROMPT"`. Displayed via `questionary.select`
(metron-tagger pattern; small dep, nicer than raw prompt). Fallback to plain
`input()` if `questionary` is unavailable or stdin isn't a TTY.

```
Ambiguous match for path/to/issue.cbz
  Existing: series='Foo Comics' issue=#5 year=2020 publisher='Quality Comics'

  ❯ 1. Foo Comics #5 (2020)         score=0.78  [metron:42]
        publisher='Quality Comics', pages=24, cover_date=2020-04-01
        https://metron.cloud/issue/foo-comics-2018-5
    2. Foo Comics (Vol. 2) #5       score=0.72  [metron:103]
        publisher='Quality Comics', pages=22, cover_date=2018-04-01
        https://metron.cloud/issue/foo-comics-vol-2-5
    3. Foo Comics Annual #5         score=0.55  [metron:200]
        publisher='Other Press', pages=48, cover_date=2020-12-01
        https://metron.cloud/issue/foo-comics-annual-5

    s. Skip this file
    m. Enter ID manually
    q. Abort entire run

  Choose:
```

Keys handled: `1`–`9` for candidate index, `s` skip, `m` manual id (re-prompts
for `<source>:<id>`), `q` quit (raises a `KeyboardInterrupt`-style abort).

Display rules:

- Show top 9 candidates max. Score below `min_confidence` → not shown.
- Score formatting: two decimals.
- The candidate's `cover_score` is shown in parens after the score when
  hashing was invoked: `score=0.78 (cov=0.95)`.
- The `url` field is a best-effort canonical link (built by
  `IDENTIFIER_PARTS_MAP` from
  [comicbox/identifiers/identifiers.py:112](../../comicbox/identifiers/identifiers.py:112)).
- If `--terse` (or comicbox's existing `-Q` quiet) is set, drop publisher /
  pages / date lines; keep series, score, id, url.

Per-comic timeout for the prompt: configurable, default `300s` (5 min). Past
that, treat as `s` skip and log a warning. Prevents bulk runs from getting
stuck on a stale terminal.

## Programmatic candidate-selection API

For codex-style integrations that drive the matcher without a TTY:

```python
SelectorResult = tuple[Literal["choose", "skip", "manual", "abort"], int | str | None]
# ("choose", candidate_index) | ("skip", None) | ("manual", "metron:42") | ("abort", None)

SelectorCallback = Callable[[ComicProfile, Sequence[Candidate], SelectorContext], SelectorResult]

@dataclass(frozen=True, slots=True)
class SelectorContext:
    file_path: Path
    source: str                # "metron"
    settings: ComicboxSettings # full settings, in case the callback wants thresholds etc.
    triggered_hashing: bool
```

Wiring:

```python
Comicbox(path, online_selector=my_callback)
# also accepted on the Runner config so the CLI can register an alternative
```

Default selector: the CLI prompt UX above.
Codex selector (out of tree): receives the candidates, applies the codex's
own logic, returns `("choose", i)` or `("skip", None)` etc.

The callback runs **inside** the rate-limit-respecting per-source flow, so
implementations can take their time without hammering APIs.

## Failure modes & logging

| Situation | Level | Message shape |
|---|---|---|
| No candidate clears `min_confidence` | INFO | `"<file>: no online match for <source> (best=<score>)"` |
| Top candidate < `confidence_threshold`, prompt suppressed | INFO | `"<file>: <source> ambiguous, skipped (--skip-multiple)"` |
| Hash invocation failed (cover unfetchable) | WARNING | `"<file>: cover hash failed for <source>:<id>: <reason>"`; matcher continues with metadata-only score |
| Metron `cv_id` ≠ independent CV match | WARNING | (defined in Phase 3) |
| User aborts via `q` | — | clean exit |
| Prompt timeout | WARNING | `"<file>: prompt timeout after 300s, skipping"` |

## Test approach (preview)

- **Signal unit tests**: each `s_*` function has table-driven cases including
  edge inputs (empty, missing, weird unicode in titles).
- **Score blending**: snapshot tests against fixture (`profile`,
  `candidates`) → expected `score`s.
- **Policy decision tests**: every cell of the policy matrix exercised
  against synthetic candidate sets.
- **Prompt UX**: smoke test that the prompt renders for a known input;
  selection logic tested via the callback API (no TTY needed).
- **Calibration harness**: separate repo asset (or `tests/fixtures/online/`)
  with the curated 100-comic set; CI doesn't run it unconditionally.

## Resolved Phase 4 questions

- Hash algorithm: pHash via `imagehash`, 64-bit (set in Phase 1).
- Hash threshold: Hamming 10 for "same cover" hard-match; blended into the
  score via `s_cover = 1 - hamming/64` for soft-match.
- Default `confidence_threshold`: `0.85` (placeholder; calibrated later).
- Default `min_confidence`: `0.50` (placeholder; calibrated later).
- Auto-write behaviour at zero candidates ≥ `min_confidence`: log at INFO,
  continue (set in Phase 2 review).
- Cover hashing only when ambiguous, not always (set above).
- Programmatic selector via callback (set above).
- `min_confidence` exposure: **internal only**; not a CLI flag or config knob.
  May be exposed later if power users need it.
- `disambiguation_margin` and `top_k_for_hashing`: **internal constants**.
- Cross-source cover hashing scope: **independent per source** — each source
  runs its own matcher with its own candidates.
- Variant cover handling: hash against **primary cover only** for v1.
  Variant fallback is a deferred enhancement — see "Deferred enhancements"
  below.
- Issue-string normalization: yes when integer-parseable. `001`, `01`,
  `1` all collapse to `1` for `issue_int`; non-numeric forms (`1a`, `1.5`,
  `0`) keep their string form for `s_issue`.

## Open questions for Phase 5

- Implementation choice for string similarity (rapidfuzz vs difflib).
- Where the cover-hash cache file lives within the cache dir.
- Whether the calibration harness ships with the codebase or stays external.
- Concrete prompt UX library (`questionary` proposed; alternative `rich.prompt`).

## Deferred enhancements (post-v1)

- **Variant cover fallback.** When the primary cover hash misses for a
  high-metadata-score candidate (e.g. metadata says it's the right issue but
  the local file is a known variant edition), as a fallback fetch the
  candidate's known variant covers (CV `associated_images`, GCD's
  `variant_of` chain) and re-hash. If a variant matches, accept the issue
  with a note about which variant it is. Cost-bounded (only triggered on
  primary-hash miss for otherwise-strong candidates), but adds API calls and
  cache pressure. Worth shipping if real-world miss-rate data justifies it;
  defer until then.
