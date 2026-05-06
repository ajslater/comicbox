# Online Tagging — Follow-ups

Single source of truth for everything that came up during M1–M7
implementation but was deferred from the v1 scope. Grouped so review
can happen one section at a time.

Marker conventions:

- ⭐ — high impact / user-visible quality issue.
- 🔍 — needs investigation / dialogue before implementing.
- ⚙️ — internals; users won't notice but devs will appreciate.

## A. Search quality

- ⭐ **±1 year retry on miss.** When the year-exact search returns
  zero candidates, retry with a relaxed year filter (`year ± 1`
  for Metron, `cover_date:Y-1-01-01|Y+1-12-31` for CV). Cover-date
  drift (cover dated the month after publication) is real and
  trivially excludes valid hits.
- 🔍 **Possible fuzzy-search expansion.** Beyond series/issue/year:
  publisher hints, series-name normalization (strip "vol. N"
  suffixes before sending), title-substring fallback, "what if the
  user has a typo." Worth listing what we *could* try and which
  ones are worth the API budget.
    - **Punctuation gap (real, observed).** Both Metron and CV use
      icontains-style filters that treat punctuation literally —
      "GI Joe" extracted from a filename will NOT match a stored
      "G.I. Joe" because "GI" is not a substring of "G.I.". Our
      filename parse strips dots in initialisms; the canonical
      stored name keeps them. Options to consider: (a) keep dots in
      the filename parse (changes parser behavior across the
      codebase); (b) on zero-result series_list, retry with a
      dot-injected variant of the query (heuristic, e.g. single
      letters get trailing dots); (c) per-source punctuation
      normalization in the search step. The reverse failure exists
      too — a filename "G.I. Joe" against a stored "GI Joe" —
      though it's less common. Pick a strategy that doesn't
      explode the API call count.
- **Volume number for search.** Phase 2 noted volume isn't in
  `ComicProfile` today. mokkari's `issues_list` accepts a `volume`
  filter; CV doesn't have a clean per-issue volume filter (we'd
  fold it into the volume search). Useful when a user has multiple
  series sharing a name (e.g. multiple "Spider-Man" volumes).
- **Cross-source confirmation logging.** When Metron's stored
  `cv_id` field disagrees with our independent ComicVine match,
  log at WARNING with both ids visible. Phase 3 declared this; M6
  punted because the cross-validation needs a place to live in
  the pipeline (probably a post-merge computed step).

## B. Match resolution UX (dialogue topic)

- 🔍 ⭐ **Review the Match Resolution Policy table and flag set.**
  Current state:
    - `--confidence-threshold` (default 0.85): top score ≥ this
      auto-writes when the gap to runner-up is ≥ 0.10.
    - `--accept-only`: when there's exactly one candidate above
      `min_confidence` (0.50), accept it (without prompting).
    - `--skip-multiple`: when more than one candidate is above
      `min_confidence`, skip the file (without prompting).
    - Default: prompt for everything ambiguous.

  The user noted this is confusing in its current form. Possible
  reframings to discuss:
    - One simpler "policy" enum: `--policy auto|prompt|skip|aggressive`,
      where `aggressive` means "always pick highest viable score
      without prompting."
    - Better defaults so most invocations need no flags: e.g. "always
      auto-write high scores; prompt only if there's no clear winner."
    - Show a worked-example table of what each flag combination does
      against a sample candidate set, in the help epilog.

  This needs a back-and-forth with proposed table layouts before
  picking one.

- **5-minute prompt timeout.** Spec'd in
  [04-match-resolution-spec.md](04-match-resolution-spec.md) but not
  implemented in M5. `signal.SIGALRM` is platform-conditional;
  `select.select` on stdin would work cross-platform. Useful for
  unattended bulk runs that hit a non-`--skip-multiple` ambiguous
  match and would otherwise hang.

## C. Field coverage

The bulk of the rich-transform work landed in commit `c4c867a`:
characters, teams, arcs, locations, universes, genres, credits with
roles, prices, stories, reprints, cross-source identifiers, plus
nh3-backed HTML sanitization for description fields. What remains:

- **Metron variants.** `Issue.variants` (list of `{id, name, sku,
  upc, image}`) is not mapped. Comicbox has no first-class variant
  schema today — decide whether to attach as a sub-collection on
  the issue, surface as alternate cover URLs, or ignore.
- **ComicVine `publisher` field.** Full `Issue.publisher` (with
  id+name) exists on the CV Issue model but the rich transform
  doesn't map it. Trivial add to `comicvine_api/__init__.py`'s
  blocks tuple.
- **ComicVine `associated_images` (variant covers).** CV exposes
  variant covers via `associated_images`; we currently take only
  the primary `image`. See also "Variant cover fallback for
  hashing" under section D — these are likely paired work.

## D. Source coverage

- **GCD via Grayven.** Architected for inclusion; ships as a
  focused PR when Grayven hits v1.0 (currently 0.5.0, pre-1.0).
  Loose-string fields (`publication_str`, `on_sale_str`, etc.)
  need caller-side parsing.
- **Variant cover fallback for hashing.** Phase 4 deferred. When
  the primary cover hash misses for an otherwise-strong candidate,
  fetch known variant covers (CV `associated_images`, GCD's
  `variant_of` chain) and re-hash. Cost-bounded — only kicks in on
  primary-hash miss for high-metadata candidates.

## E. Calibration & defaults

- **Default `--confidence-threshold` and `min_confidence`.**
  Currently placeholders (0.85 and 0.50). Calibrate against a
  curated fixture set of known-correct matches and tune so ≥95%
  of correct matches clear `confidence_threshold` and ≥99% clear
  `min_confidence`.
- **Calibration harness.** `tests/calibration/run.py` was specced
  in Phase 5 but not built. Loads a `fixtures.json` (gitignored,
  per-developer), runs the matcher against each, reports
  matched / wrong / no-match grouped by score band. `make
  calibrate` target.
- **VCR cassettes for integration tests.** Recorded once with
  real credentials, replayed in CI. Currently every test mocks
  the upstream client directly.

## F. Internals

- ⚙️ **`--api-url metron:<url>` is currently a no-op.** mokkari's
  `api()` factory has no URL-override parameter (only `dev_mode`
  for the dev API). Either upstream a feature request to mokkari
  or document the limitation in CLI help.
- ⚙️ **Expose `min_confidence` as a CLI flag.** Currently internal;
  power users tuning thresholds may want it. Argument against:
  two thresholds confuse users, especially given (B) above.
- ⚙️ **Expose `disambiguation_margin` and `top_k_for_hashing`.**
  Internal constants today (0.10 and 5). Defer until calibration
  data justifies user-facing knobs.
- ⚙️ **`--id` series-id form.** metron-tagger's `--id` is a series
  id (constrains search). Ours is issue-id. If users want
  series-constrained search, add `--series-id <db>:<id>` later.
- ⚙️ **Cleanup of `LegacyNestedMDStringSetField` /
  `XmlLegacyNestedMDStringSetField`.** Now that
  `MetadataSources.LEGACY_NESTED` is removed (M1), these field
  classes' `is_nested_metadata` detection is unused. The fields
  still serialize PDF `keywords` sanely; check whether the
  detection branch can be deleted.

## G. Architecture (post-feature)

- **Flavor A plugin refactor.** Consolidate each format
  (ComicInfo, MetronInfo, ComicBookInfo, CoMet, ComicTagger, PDF,
  Metron API, ComicVine API) into self-contained modules owning
  schema + transforms + source registration + format
  registration. No dynamic discovery — just better internal
  organisation. Plan to be drafted post-online-tagging with the
  M2/M6 integration experience as input.

## H. M7 / parallelism

- **Real-load stress test.** The unit test verifies the prompt
  lock holds; we haven't actually run `-j 8` against 1000 files
  with live API access. Validate rate-limiter compliance and
  prompt UX under load before declaring M7 production-ready.
- **`-j` documentation.** CLI help mentions the flag exists but
  doesn't yet recommend a sensible value or warn about thrashing
  the rate limiter. Add notes after stress-testing.

---

## Maintenance reminder

When any item lands, move its bullet point out of this file and
into a NEWS.md entry under the version that ships it. Don't let the
list rot.
