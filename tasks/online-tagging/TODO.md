# Online Tagging — TODO

Single source of truth for everything that came up during M1–M7
implementation but was deferred from the v1 scope. Sections are roughly
in order of priority: section 1 is the next thing to ship, section 3 is
the most distant.

Marker conventions:

- ⭐ — high impact / user-visible quality issue.
- 🔍 — needs investigation / dialogue before implementing.
- ⚙️ — internals; users won't notice but devs will appreciate.
- 🚫 — explicitly declined / deferred indefinitely; here for the record.


## 1. Calibration & defaults

- ✅ **Run calibration against a real fixture set.** DONE — three
  calibrations now in the books:
  - **Phase B** (339 fixtures, labeled): 100% accuracy under `fast`.
    See [`calibration-notes/2026-05-11-phase-b.md`](calibration-notes/2026-05-11-phase-b.md).
  - **Slimlib** (500 fixtures, stratified one-per-series, thumbnail
    covers): 96.9% CV, metadata-signal-only validation. See
    [`calibration-notes/2026-05-12-slimlib-500.md`](calibration-notes/2026-05-12-slimlib-500.md).
  - **Bigmedia** (247 fixtures, full-cover, Big-Two-heavy): 94.3%
    CV / 97.0% Metron / 100% Metron auto-write band. See
    [`calibration-notes/2026-05-14-bigmedia-247.md`](calibration-notes/2026-05-14-bigmedia-247.md).
- ✅ **Tune `--confidence-threshold` and `min_confidence` from data.**
  DONE. `confidence_threshold` settled at 0.95 (was 0.85 — calibration
  showed 7% wrong auto-writes in 0.85-0.95 band, mostly wrong-volume
  picks for series with reboots). `min_confidence` stays at 0.50.
  Phase E added a `solo_confidence_threshold` floor (0.95 default) to
  close the silent-failure path when the matcher returns a single
  below-threshold candidate.
- **VCR cassettes for integration tests.** Still not done.
  (Optional — the three calibration sets now cover most of what VCR
  cassettes would.)
- ✅ **Default policy choice.** DONE. `normal` validated across all
  three calibration sets; no false-positive write rate that justified
  retreating to `strict`. Phase E's solo-confidence floor further
  hardened NORMAL against the worst silent-failure pattern.
- ✅ **Cover-hash calibration.** DONE via the bigmedia 247-fixture
  run (full covers, cover_quality: full in the fixture set). 97.6%
  CV auto-write band with cover hashing firing where appropriate.
  Phase G (2026-05-14) tightened the `_COVER_DIFF_NOISE_MARGIN` from
  0.05 → 0.03 based on bigmedia tied-dupe analysis.


## 2. Stress test & parallelism

- ✅ **Real-load stress test (rate-limiter compliance).** Done
  2026-05-15. -j 8, 20 fixtures, cold cache → PASS. Metron pinned at
  20.10/min (exactly its 20/min cap); CV at 8.23/min (well under).
  No tracebacks, exit 0. See
  [`calibration-notes/2026-05-15-stress-test.md`](calibration-notes/2026-05-15-stress-test.md).
  Harness lives at `tests/stress/`; run via `make stress`.
- ✅ **Prompt UX under -j.** Done 2026-05-15. 16 fixtures, -j 8,
  `--policy always-prompt --force-search` forces every candidate
  through PROMPT. 23 selector calls across 8 distinct threads, **0
  overlapping intervals**, no deadlocks. See
  [`calibration-notes/2026-05-15-prompt-ux.md`](calibration-notes/2026-05-15-prompt-ux.md).
  Harness at `tests/stress/prompt_ux.py`; run via
  `make stress-prompt-ux`.
- **Larger stress run (50-100 fixtures).** The 20-fixture run was
  Metron-bound; bigger runs exercise CV's 200/hr cap and a different
  code path (simyan's pyrate_limiter backoff vs mokkari's raise-and-
  retry). Worth doing before declaring M7 fully shipped; doesn't
  block doc updates.
- **`-j` documentation.** Done in the follow-up commit that closes
  this section — CLI help recommends defaults based on the stress
  data (default 1, sweet-spot 4, spec'd-target 8 with caveat). See
  the stress-test calibration note for the underlying numbers.

**Bugs surfaced by the stress run (separate follow-ups):**

- `Metron.series_list` at `comicbox/online/sources/metron.py:254` is
  **not** wrapped by `@with_retry()`. Six terminal rate-limit
  failures in the stress run came from this gap. Audit ComicVine's
  equivalent path for the same issue.
- `_MAX_RATE_LIMIT_RETRIES = 5` is sometimes too small under -j 8
  contention. Bumping to 8 or making it `-j`-aware are both worth
  measuring before deciding the shape.


## 3. API budget

✅ **DONE** — three planned phases shipped, plus four additional phases
(D / E / F / G) added in flight based on calibration data. Detailed
status in [`06-api-budget-spec.md`](06-api-budget-spec.md) and
[`META-PLAN.md`](META-PLAN.md).

- ✅ **Phase A — Build** (commit `a754f6a`). Dormant levers.
- ✅ **Phase B — Calibrate** (commit `99d794e`). Pinned thresholds at
  pre-filter 0.4 / 0.7 (balanced / fast), max-volumes=5, top-K=5. See
  [`calibration-notes/2026-05-11-phase-b.md`](calibration-notes/2026-05-11-phase-b.md).
- ✅ **Phase C — Integrate & ship** (commit `c2b2ca6`). `--api-budget`
  CLI flag, auto-engagement, user doc.
- ✅ **Phase D — Per-budget search cap + chunked-run scaffolding**
  (commit `241fa04`). Added `--resume`, `sample.py`, `label_metron.py`,
  `summarize.py`. Phase D was added beyond the original three-phase
  plan when slimlib-scale calibration motivated chunked execution.
- ✅ **Phase E — Solo-viable confidence floor** (commit `e7bfdbd`).
  New `solo_confidence_threshold` setting (default 0.95) closes the
  worst silent-failure pattern (solo candidate below threshold
  auto-writes wrong answer).
- ✅ **Phase F — Year-signal decay** (commit `602378d`). Replaces the
  binary-cliff at year-diff ≥ 3 with smooth linear decay to 0.0 at
  diff=7. Preserves original anchors (1.0 / 0.7 / 0.4 for diff 0/1/2).
- ✅ **Phase G — Tighten cover-diff noise margin** (commit `fe7bf90`).
  `_COVER_DIFF_NOISE_MARGIN` 0.05 → 0.03 based on bigmedia tied-dupe
  cases (Fallen Son, Hawkeye Freefall).
- ❌ **Phase H — CV broadening retry on weak top quick-score** —
  REVERTED. Landed as `f772d75`, reverted by `62a5725`. Rev 2 with
  source-aware discovery_pass tiebreak (`35ff22f`) also reverted by
  `b407815` after producing 0 flips on bigmedia. The "right answer
  not in CV's top-5" problem (7 bigmedia misses) is therefore still
  open; see calibration follow-up below.
- ❌ **Phase I — Cover-diff relative threshold** — REVERTED. Landed
  as `d2a07e5`, reverted by `b33da25`. Bigmedia diff showed silent
  CV accuracy regression (94.6% → 89.9%) on "specific trade
  collection vs canonical series volume" pattern (Black Widow by
  Kelly Thompson, Conan by Jim Zub, Wolverine by Claremont, Elektra
  by Greg Rucka, etc.). Phase G's absolute 0.03 margin is restored.
  Hawkeye Freefall reverts to noise (worth 1 fixture vs 14
  regressions Phase G handled correctly).
- ✅ **Phase J — Adaptive top-K for cover hashing** (commit
  `7a44fa4`). Replaces fixed top-K with a quality-adaptive cutoff so
  cover hashing engages on the right candidate set even when the
  initial metadata-score distribution is flat.
- ✅ **Phase K rev 2 — Signal-content-aware metadata renormalisation**
  (commit `916a488`; rev 1 at `7867459` superseded). A metadata
  signal is dropped from the denominator only when BOTH profile and
  candidate sides are empty/None. Asymmetric absence keeps the
  signal in the denominator and lets the signal function's
  missing-data branch penalise the under-informed candidate
  (s_year=0.3, s_publisher=0.5, s_pages=0.6 asymmetric). Rev 1 had
  dropped signals on either-side-missing and let canonical-named
  series volumes (Conan the Barbarian) beat the actual trade-
  collection answer for thumbnail-only profiles; rev 2 fixes that
  while preserving the Wolverine prompt-UX win (both-None →
  signals dropped → renormalised to 1.0).

**Calibration follow-ups still open** (see
[`META-PLAN.md`](META-PLAN.md) "Calibration follow-ups" section):
- CLI surface for `solo_confidence_threshold` (low priority)
- Bigmedia re-run after Phase H/I reverts + Phase J/K rev 2 to
  confirm recovery toward the pre-HI ~263-correct baseline and lock
  in the K-rev-2 trade-collection ordering empirically. Manual spot-
  checks (Conan by Jim Zub, Wolverine thumbnail) confirmed; full
  bigmedia sweep still pending.
- "Right answer not in CV's top-5" search-relevance problem (the
  original Phase H motivation) remains open after two failed
  broadening attempts. Needs a different approach than broadening
  every weak-top query — likely query-side (more specific search
  terms) or post-hoc (only broaden when we can detect the candidate
  set is wrong, not just weak).


## 4. Architecture (post-feature)

- **Flavor A plugin refactor.** Consolidate each format (ComicInfo,
  MetronInfo, ComicBookInfo, CoMet, ComicTagger, PDF, Metron API,
  ComicVine API) into self-contained modules owning schema +
  transforms + source registration + format registration. No dynamic
  discovery — just better internal organisation. Plan to be drafted
  post-online-tagging with the M2/M6 integration experience as input.


---

## Maintenance reminder

When any item lands, move its bullet point out of this file and into a
NEWS.md entry under the version that ships it. Don't let the list rot.

---

# Deferred Indefinitely

## Search quality

- 🚫 **Client-side fuzzy-search expansion (declined).** Stance: rely
  on the online databases' own search fuzziness. Don't try to patch
  around DB limitations with client-side query rewrites (publisher
  hints, "vol. N" suffix stripping, title-substring fallback,
  typo-tolerant variants, etc.) unless we have a strong signal that a
  particular technique is profitable. Neither metron-tagger nor
  comictagger does this; both rely on the DB's search behavior and
  ship. We should follow suit.

  Known limitation worth documenting (not fixing client-side):
  **the punctuation gap.** Both Metron and CV use icontains-style
  filters that treat punctuation literally — "GI Joe" from a filename
  will NOT match a stored "G.I. Joe" because "GI" is not a substring
  of "G.I.". Our filename parse strips dots in initialisms; the
  canonical stored name keeps them. The right fix for this lives
  upstream (DB fuzz) or in the filename parser (don't strip dots), not
  in client-side query expansion.
- 🔍 **Retry-relaxation order: volume vs year.** Current order is
  `(year, volume) → year ±1 → drop volume → drop volume + year ±1`.
  This treats volume as more reliable than year — but for an
  undertagged comic the opposite might be true: scanners often drop
  or guess volume entirely, while cover-date drift is a ±1 thing that
  doesn't make the year *wrong*, just adjacent. Worth A/B-ing with
  real-world miss data: try `(year, volume) → drop volume → year ±1
  → drop both` and see which order finds more correct matches with
  fewer API calls. Decision needs miss-rate telemetry from a
  calibration set, not a guess.
- **Series-list volume narrowing (Metron).** When `profile.volume` is
  set, we *could* also pass it to `series_list` to pre-filter the
  candidate-series set before fan-out (Metron exposes `volume` as a
  `NumberFilter` on `/series/`). Skipped for now — multi-volume
  series sharing a name aren't common enough in practice to justify
  the extra complexity, and the issue-level `series_volume` filter
  (already wired on the issue lookup pass) takes care of
  disambiguation downstream. Revisit if real-world data shows
  series_list returns >1 same-named series often.


## Field coverage — variants

- **Metron variants.** `Issue.variants` (list of `{id, name, sku, upc,
  image}`) is not mapped. Comicbox has no first-class variant schema
  today — decide whether to attach as a sub-collection on the issue,
  surface as alternate cover URLs, or ignore.
- **ComicVine `associated_images` (variant covers).** CV exposes
  variant covers via `associated_images`; we currently take only the
  primary `image`. Likely paired work with the variant cover fallback
  for hashing below.
- **Variant cover fallback for hashing.** Phase 4 deferred. When the
  primary cover hash misses for an otherwise-strong candidate, fetch
  known variant covers (CV `associated_images`, GCD's `variant_of`
  chain) and re-hash. Cost-bounded — only kicks in on primary-hash
  miss for high-metadata candidates.


## Other online databases

- **GCD via Grayven.** Architected for inclusion; ships as a focused
  PR when Grayven hits v1.0 (currently 0.5.0, pre-1.0). Loose-string
  fields (`publication_str`, `on_sale_str`, etc.) need caller-side
  parsing.


## Internals

Mostly explicitly-declined exposure of internal knobs.

- ⚙️ **mokkari `base_url` upstream feature request.**
  `--api-url metron:<url>` is now documented as a no-op in CLI help
  and warns loudly at runtime; the long-term fix is upstreaming a
  `base_url` override into mokkari's `api()` factory. No
  comicbox-side work beyond raising the issue.
- 🚫 **Declined: expose `min_confidence`.** Two thresholds would
  confuse users; the new policy scheme renders this unnecessary.
- 🚫 **Declined: expose `disambiguation_margin` / `top_k_for_hashing`.**
  Power-user knobs without calibration data behind them. Per-source
  override machinery for `min_confidence` and `disambiguation_margin`
  is wired internally (see section 1) so the option is open if
  calibration ever justifies it.
