# Online Tagging — To Do

Single source of truth for everything that came up during M1–M7
implementation but was deferred from the v1 scope. Grouped so review
can happen one section at a time.

Marker conventions:

- ⭐ — high impact / user-visible quality issue.
- 🔍 — needs investigation / dialogue before implementing.
- ⚙️ — internals; users won't notice but devs will appreciate.

## A. Search quality

- 🚫 **Client-side fuzzy-search expansion (declined).** Stance:
  rely on the online databases' own search fuzziness. Don't try to
  patch around DB limitations with client-side query rewrites
  (publisher hints, "vol. N" suffix stripping, title-substring
  fallback, typo-tolerant variants, etc.) unless we have a strong
  signal that a particular technique is profitable. Neither
  metron-tagger nor comictagger does this; both rely on the DB's
  search behavior and ship. We should follow suit.

  Known limitation worth documenting (not fixing client-side):
  **the punctuation gap.** Both Metron and CV use icontains-style
  filters that treat punctuation literally — "GI Joe" from a
  filename will NOT match a stored "G.I. Joe" because "GI" is not
  a substring of "G.I.". Our filename parse strips dots in
  initialisms; the canonical stored name keeps them. The right fix
  for this lives upstream (DB fuzz) or in the filename parser
  (don't strip dots), not in client-side query expansion.
- 🔍 **Retry-relaxation order: volume vs year.** Current order is
  `(year, volume) → year ±1 → drop volume → drop volume + year ±1`.
  This treats volume as more reliable than year — but for an
  undertagged comic the opposite might be true: scanners often
  drop or guess volume entirely, while cover-date drift is a
  ±1 thing that doesn't make the year *wrong*, just adjacent.
  Worth A/B-ing with real-world miss data: try `(year, volume) →
  drop volume → year ±1 → drop both` and see which order finds
  more correct matches with fewer API calls. Decision needs
  miss-rate telemetry from a calibration set, not a guess.
- **Series-list volume narrowing (Metron, deferred).** When
  `profile.volume` is set, we *could* also pass it to `series_list`
  to pre-filter the candidate-series set before fan-out (Metron
  exposes `volume` as a `NumberFilter` on `/series/`). Skipped for
  now — multi-volume series sharing a name aren't common enough
  in practice to justify the extra complexity, and the issue-level
  `series_volume` filter (already wired on the issue lookup pass)
  takes care of disambiguation downstream. Revisit if real-world
  data shows series_list returns >1 same-named series often.

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


## G. Stress Test Jobs

- **Real-load stress test.** The unit test verifies the prompt
  lock holds; we haven't actually run `-j 8` against 1000 files
  with live API access. Validate rate-limiter compliance and
  prompt UX under load before declaring M7 production-ready.
- **`-j` documentation.** CLI help mentions the flag exists but
  doesn't yet recommend a sensible value or warn about thrashing
  the rate limiter. Add notes after stress-testing.
  
## H. Architecture (post-feature)

- **Flavor A plugin refactor.** Consolidate each format
  (ComicInfo, MetronInfo, ComicBookInfo, CoMet, ComicTagger, PDF,
  Metron API, ComicVine API) into self-contained modules owning
  schema + transforms + source registration + format
  registration. No dynamic discovery — just better internal
  organisation. Plan to be drafted post-online-tagging with the
  M2/M6 integration experience as input.

---

## Maintenance reminder

When any item lands, move its bullet point out of this file and
into a NEWS.md entry under the version that ships it. Don't let the list rot.

---

# Deferred Indefinately

## Field coverage - Variants

- **Metron variants.** `Issue.variants` (list of `{id, name, sku,
  upc, image}`) is not mapped. Comicbox has no first-class variant
  schema today — decide whether to attach as a sub-collection on
  the issue, surface as alternate cover URLs, or ignore.
- **ComicVine `associated_images` (variant covers).** CV exposes
  variant covers via `associated_images`; we currently take only
  the primary `image`. See also "Variant cover fallback for
  hashing" under section D — these are likely paired work.
  
- **Variant cover fallback for hashing.** Phase 4 deferred. When
  the primary cover hash misses for an otherwise-strong candidate,
  fetch known variant covers (CV `associated_images`, GCD's
  `variant_of` chain) and re-hash. Cost-bounded — only kicks in on
  primary-hash miss for high-metadata candidates.

## Other Online Databases

- **GCD via Grayven.** Architected for inclusion; ships as a
  focused PR when Grayven hits v1.0 (currently 0.5.0, pre-1.0).
  Loose-string fields (`publication_str`, `on_sale_str`, etc.)
  need caller-side parsing.

## Internals

Mostly explicitly-declined exposure of internal knobs.

- ⚙️ **mokkari `base_url` upstream feature request.** `--api-url
  metron:<url>` is now documented as a no-op in CLI help and warns
  loudly at runtime; the long-term fix is upstreaming a `base_url`
  override into mokkari's `api()` factory. No comicbox-side work
  beyond raising the issue.
- 🚫 **Decided not to expose `min_confidence`.** Two thresholds
  would confuse users, especially given (B). Stays internal until
  the policy story in (B) settles.
- 🚫 **Decided not to expose `disambiguation_margin` /
  `top_k_for_hashing`.** Same rationale — power-user knobs without
  calibration data behind them. Revisit if calibration (E) shows
  a clearly-better value.