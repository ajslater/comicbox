# Online Tagging — TODO

Single source of truth for everything that came up during M1–M7
implementation but was deferred from the v1 scope. Sections are roughly
in order of priority: section 1 is the next thing to ship, section 4 is
the most distant.

Marker conventions:

- ⭐ — high impact / user-visible quality issue.
- 🔍 — needs investigation / dialogue before implementing.
- ⚙️ — internals; users won't notice but devs will appreciate.
- 🚫 — explicitly declined / deferred indefinitely; here for the record.


## 1. Match resolution UX

The full design has been signed off and lives in
[match-resolution-user-doc.md](match-resolution-user-doc.md). What's
left is implementation, polish, and user-facing documentation.

### Implement the new policy scheme

- ⭐ **`--unattended` and `--policy <name>` flags.** Replace the current
  `--accept-only` / `--skip-multiple` flags. `--policy` accepts
  `always-prompt|strict|normal|eager`, default `normal`. `--unattended`
  is a boolean: when set, prompts become SKIPs.
- ⭐ **Per-source override syntax** for both `--policy` and
  `--confidence-threshold` (mirrors the existing `--id <db>:<id>` and
  `--api-url <db>:<url>` pattern). Resolution: per-source > global >
  built-in default. Internal thresholds (`min_confidence`,
  `disambiguation_margin`) get the same per-source machinery internally
  even though they're not user-exposed yet.
- ⭐ **Algorithm change: redefine `eager`** as `top.score ≥ 0.85 OR
  solo_viable` so `strict ⊂ normal ⊂ eager` containment holds.
  Currently `eager` would fail to auto-write a sole 0.65 candidate that
  `normal` happily takes — wart documented in scenarios 3 and 5 of the
  user-doc.
- **Reject `--policy always-prompt --unattended`** at config-validation
  time. Nonsensical (every comic skips, no work is done) and almost
  certainly a user error.
- **No-TTY hint at startup** when interactive mode runs without a TTY
  and no programmatic prompt callback is registered. One-time log:
  *"no TTY detected; pass `--unattended` if you don't expect to see
  prompts."*
- **Distinct SKIP vs NO_MATCH counts in the end-of-run summary.**
  Currently collapsed; users can't tell "comicbox declined to choose"
  from "the database didn't know."
- **Deprecation path for legacy flags.** `--accept-only` and
  `--skip-multiple` warn-and-translate during a transition period,
  then are removed.

### User-facing documentation

- ⭐ **Clear CLI `--help` and README docs for match-resolution
  parameters.** This stuff is dense — the user shouldn't need to read
  the design doc to use it. `--help` should at minimum:
    - Spell out what each `--policy` value means in one line each.
    - Show what `--unattended` actually does (prompt → skip).
    - Include a 1-paragraph worked example or table of "you'll see
      auto-write / prompt / skip in case X."

  README should walk through one or two practical recipes
  (interactive single comic, unattended cron, library-as-codex) so
  users can copy-paste a working incantation.

### Pre-existing item

- **5-minute prompt timeout.** Spec'd in
  [04-match-resolution-spec.md](04-match-resolution-spec.md) but not
  implemented in M5. `signal.SIGALRM` is platform-conditional;
  `select.select` on stdin would work cross-platform. Useful when an
  interactive run starts and the user walks away — prompt times out
  and SKIPs rather than hanging forever. Less urgent post-`--unattended`
  (the cron-job case is now covered by the explicit flag).


## 2. Calibration & defaults

- **Default `--confidence-threshold` and `min_confidence`.** Currently
  placeholders (0.85 and 0.50). Calibrate against a curated fixture
  set of known-correct matches and tune so ≥95% of correct matches
  clear `confidence_threshold` and ≥99% clear `min_confidence`.
- **Calibration harness.** `tests/calibration/run.py` was specced in
  Phase 5 but not built. Loads a `fixtures.json` (gitignored,
  per-developer), runs the matcher against each, reports
  matched / wrong / no-match grouped by score band. `make calibrate`
  target.
- **VCR cassettes for integration tests.** Recorded once with real
  credentials, replayed in CI. Currently every test mocks the upstream
  client directly.
- **Default policy choice.** New default is `normal`, slightly more
  eager than today. If real-world calibration shows it produces a high
  false-positive write rate, retreat the default to `strict`. Decision
  belongs with the calibration harness, not a guess.


## 3. Stress test & parallelism

- **Real-load stress test.** The unit test verifies the prompt lock
  holds; we haven't actually run `-j 8` against 1000 files with live
  API access. Validate rate-limiter compliance and prompt UX under
  load before declaring M7 production-ready.
- **`-j` documentation.** CLI help mentions the flag exists but
  doesn't yet recommend a sensible value or warn about thrashing the
  rate limiter. Add notes after stress-testing.


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
