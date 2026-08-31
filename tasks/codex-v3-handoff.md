# Comicbox Schema v3.0 — Codex Handoff

**Audience:** an agent updating [codex](https://github.com/ajslater/codex) to
the paired comicbox release that ships schema v3.0. This document is
self-contained: it does not assume you saw the comicbox conversation or PRs.

**Status:** complete. Every schema v3.0 change is recorded below. The **Adoption
checklist** at the bottom is the actionable summary; read it first, then the
details you need.

## Why this exists

comicbox and codex ship paired. Schema v3.0 changes the shape of the metadata
dict that `Comicbox.get_internal_metadata()` returns, plus the on-disk comicbox
JSON/YAML serializations. There are **no compatibility shims and no
up-converter**: comicbox speaks v3 only, and a v2 document loads with its
renamed and removed fields silently ignored. Codex must be updated in the same
release cycle.

The redesign came from an audit of every supported format spec (MetronInfo v1.1,
ComicInfo v2.1 draft, ComicBookInfo 1.0, CoMet 1.1) against the v2.0 unified
schema. Two themes drove it:

1. **Comicbox was inventing structure the source specs don't have** — splitting
   single-valued fields into collections, parsing free strings into objects,
   then fabricating format tags back out of those guesses.
2. **Comicbox conflated concepts that the highest-priority format keeps
   separate** — most importantly identifiers vs URLs, and four different "this
   issue relates to another book" concepts all crammed into `reprints`.

Format priority when specs disagree: **MetronInfo > ComicInfo >>
ComicBookInfo >> CoMet / PDF / filename.**

## Versioning and detection

- JSON documents carry
  `"schema": "https://github.com/ajslater/comicbox/blob/main/schemas/v3.0/comicbox-v3.0.schema.json"`.
  v2 documents carry the `/v2.0/comicbox-v2.0.schema.json` URL.
- YAML documents carry the same `schema:` key when exported by comicbox, but
  hand-written YAML often omits it — do not rely on it being present.
- Nothing outside comicbox's own repository used schema v2, so there is no v2
  data in the wild to migrate. Comicbox JSON or YAML that codex wrote itself is
  the one exception; convert it with the field tables below, or more simply,
  re-read the comics.
- The JSON Schemas live in the comicbox package at `comicbox/schemas/v3.0/`
  (`schemas/` at the repo root is a symlink to `comicbox/schemas/`). The v2.0
  directory is retained unchanged as the published v2 contract.
- The schemas are **hand-maintained**, not generated.
  `tests/schemas/test_json_schema_drift.py` walks the Marshmallow model against
  the JSON Schema and fails on any divergence in property names, types, or enum
  values — so the JSON Schema is a trustworthy description of the real shape.

## Shape changes

### PR 1 — v3.0 scaffolding, two field deletions

| Field                       | v2                  | v3          |
| --------------------------- | ------------------- | ----------- |
| `comicbox.alternate_images` | `[string]`          | **removed** |
| `comicbox.critical_rating`  | `number` (0–5, 1dp) | **removed** |

- `alternate_images` was dead: no format transform produced or consumed it since
  the ComicTagger format was dropped. Nothing to migrate.
- `critical_rating` was orphaned: comicbox's own schema README recorded that it
  "no longer maps to any format". All ratings flow through
  `community_rating.average_rating` (0–5, one decimal place) and
  `community_rating.rating_count`.

**Codex impact:** if codex has a column, serializer field, or import mapping for
either name, drop it. If codex used `critical_rating` for a _user's personal_
rating, that is now codex-side state with no comicbox representation — comicbox
will neither read nor write it.

### PR 2 — canonical role vocabulary

`comicbox.credits.<person>.roles` keys are now always MetronInfo role names. The
shape is unchanged; the **values of the keys** change, so any codex table,
filter, or migration keyed on role strings needs updating.

| Role key seen in v2                                      | v3 key       |
| -------------------------------------------------------- | ------------ |
| `Colorist`, `colorist`, `Colourist`, `Colorer`           | `Colorist`   |
| `CoverArtist`, `Cover Artist`, `colorDesigner`, `Covers` | `Cover`      |
| `Writer`, `writer`, `Author`                             | `Writer`     |
| `Penciller`, `penciller`, `Penciler`, `Pencils`          | `Penciller`  |
| `Inker`, `inker`, `Inks`                                 | `Inker`      |
| `Letterer`, `letterer`, `Letters`                        | `Letterer`   |
| `Editor`, `editor`, `Edits`, `Editing`                   | `Editor`     |
| `Translator`, `Translation`                              | `Translator` |
| `Breakdowns` (was folded into `Penciller`)               | `Breakdowns` |
| `Finishes` (was folded into `Inker`)                     | `Finishes`   |
| `Plotter`                                                | `Plot`       |
| `Scripter`, `Script`                                     | `Script`     |
| `creator`                                                | `Creator`    |
| `Painter`, `Painting`                                    | `Painter`    |

The full canonical vocabulary is `MetronRoleEnum` in
`comicbox/enums/metroninfo.py` — 42 roles: Writer, Script, Story, Plot,
Interviewer, Artist, Penciller, Breakdowns, Illustrator, Layouts, Inker,
Embellisher, Finishes, Ink Assists, Colorist, Color Separations, Color Assists,
Color Flats, Digital Art Technician, Gray Tone, Letterer, Cover, Editor,
Consulting Editor, Assistant Editor, Associate Editor, Group Editor, Senior
Editor, Managing Editor, Collection Editor, Production, Designer, Logo Design,
Translator, Supervising Editor, Executive Editor, Editor In Chief, President,
Publisher, Chief Creative Officer, Executive Producer, Other. Plus two comicbox
extras with no Metron equivalent: `Painter` and `Creator`. **Roles comicbox does
not recognize are still stored verbatim (titlecased)** — the vocabulary is not
closed, so do not add a database constraint that rejects unknown roles.

**Codex migration:** map existing role rows through the table above. A
case-insensitive match on the old spelling is enough; the only rows that change
meaning rather than spelling are `Breakdowns`, `Finishes`, `Plotter` and
`Scripter`, which used to be stored as the coarser role.

### PR 3 — canonical age ratings, `manga` split from reading direction

**`comicbox.age_rating`** is now always one of MetronInfo's seven values:
`Unknown`, `Everyone`, `Teen`, `Teen Plus`, `Mature`, `Explicit`, `Adult`. It
used to store whichever vocabulary arrived — ComicInfo's 15 values, or a Marvel,
DC or generic publisher rating. As with roles, an unrecognized rating is stored
verbatim, so do not constrain the column to the seven values.

| Rating seen in v2                                                                          | v3          |
| ------------------------------------------------------------------------------------------ | ----------- |
| `Everyone`, `Everyone 10+`, `G`, `Kids to Adults`, `Early Childhood`, `All Ages`, `E`, `A` | `Everyone`  |
| `Teen`, `PG`, `PG13`, `13+`, `T`, `PSR`                                                    | `Teen`      |
| `MA15+`, `Teen Plus`, `T+`, `PG+`, `PSR+`, `Parental Advisory`, `15+`                      | `Teen Plus` |
| `Mature 17+`, `M`, `Mature`, `R18+`, `R`, `17+`, `Max`                                     | `Mature`    |
| `X18+`, `X`, `XXX`, `ExplicitContent`, `Max: Explicit Content`, `Violent`                  | `Explicit`  |
| `Adults Only 18+`, `Adult`, `Porn`, `Sexually Explicit`                                    | `Adult`     |
| `Unknown`, `Rating Pending`                                                                | `Unknown`   |

This is lossy in one direction: a ComicInfo library that distinguished
`Everyone 10+` from `Everyone` no longer can. That was the accepted trade for a
single scale across formats. ComicInfo files are still written with ComicInfo's
own vocabulary, so `Teen Plus` writes back as `MA15+`.

**`comicbox.manga`** is now `Yes`, `No` or `Unknown` — never
`YesAndRightToLeft`. ComicInfo's compound value splits on read into `manga: Yes`
plus `reading_direction: rtl`, and the two recombine when writing ComicInfo.

| v2 `manga`          | v3 `manga` | v3 `reading_direction` |
| ------------------- | ---------- | ---------------------- |
| `Yes`               | `Yes`      | unchanged              |
| `YesAndRightToLeft` | `Yes`      | `rtl`                  |
| `No`                | `No`       | unchanged              |

A ComicInfo `Manga` of `Unknown` used to be read as `No`, asserting a book was
not manga when the file said it did not know; it now reads as `Unknown`. If
codex derives "read right to left" from `manga`, read `reading_direction`
instead — it is also what CoMet supplies, for non-manga books too.

### PR 4 — `credit_primaries` folded into the role

The top-level `comicbox.credit_primaries` map is **removed**. The flag it held
now lives on the role object it describes.

```yaml
# v2
credits:
    Joe Orlando: { roles: { Writer: {} } }
credit_primaries:
    Writer: Joe Orlando

# v3
credits:
    Joe Orlando: { roles: { Writer: { primary: true } } }
```

The role object is otherwise unchanged — it already carried `identifiers` — so
`credits.<person>.roles.<role>` is now `{identifiers?, primary?}`.

**This is a semantic fix, not just a move.** `credit_primaries` was keyed by
role alone (`{role: person}`), and the write side matched it by comparing the
person's name to every role they held. A person who was the primary Writer was
therefore also written as the primary Inker, Colorist and anything else they did
on the book. The flag now belongs to the (person, role) pair, which is what
ComicBookInfo's per-credit `primary` field always meant.

**Codex migration:** for each stored `credit_primaries` entry `{role: person}`,
set `primary` on that person's row for that role only. Only ComicBookInfo
supplies the flag; no other format reads or writes it.

### PR 5 — identifiers split from urls

The largest shape change. MetronInfo keeps its `IDS` and `URLs` in separate
lists, each with its own primary flag, and comicbox now does the same.

```yaml
# v2
identifier_primary_source:
    source: comicvine
    url: https://comicvine.gamespot.com/ # synthesized, never from the file
identifiers:
    comicvine:
        key: "145269"
        url: https://comicvine.gamespot.com/captain-science-1/4000-145269/

# v3
primary_id_source: comicvine
identifiers:
    comicvine:
        key: "145269"
urls:
    - https://comicvine.gamespot.com/captain-science-1/4000-145269/ # verbatim
    - https://comicvine.gamespot.com/c/4000-145269/ # derived from the key
```

| v2                                 | v3                                                       |
| ---------------------------------- | -------------------------------------------------------- |
| `identifiers.<source>.key`         | unchanged                                                |
| `identifiers.<source>.url`         | moved into the top-level `urls` list                     |
| `identifier_primary_source.source` | `primary_id_source` (a plain string)                     |
| `identifier_primary_source.url`    | **gone** — it was always synthesized                     |
| —                                  | `urls: [string]`, order preserved, file's own urls first |
| —                                  | `identifiers.<source>.id_type`, optional (see below)     |

The same applies to **every** nested identifiers map: `series`, `publisher`,
`imprint`, `arcs`, `characters`, `teams`, `locations`, `genres`, `stories`,
`tags`, `universes`, `credits`, `credits.*.roles`, `reprints`. Only the top
level gains `urls`.

**`id_type`** is a new optional field on an identifier, recorded only when the
key's type differs from the one implied by where it sits. Almost every
identifier omits it: an id under `series` is a series id. It exists for
hand-tagged keys like `series:178012` written at the issue level, where the type
decides which url the key builds.

**Derivation still happens, it is just no longer stored twice.** Reading a
comic, comicbox fills a missing identifier from a url it recognizes, and a
missing url from an identifier's key. So codex sees both, as before. Two
behavior changes come with it:

- A url from a site comicbox doesn't recognize is kept verbatim in `urls` and no
  longer invents an identifier keyed by its hostname. v2 produced entries like
  `identifiers: {"bar.foo": {"url": "https://bar.foo"}}`; those are gone.
- An explicit id always beats a url-derived one. For several databases the url
  path is a slug rather than the id.

**Codex migration:** move each `identifiers.*.url` into a top-level `urls` list,
rename `identifier_primary_source` to `primary_id_source` keeping only its
`source` string, and drop identifier rows whose source is a bare hostname (keep
their url).

### PR 6 — single-valued format tags

No comicbox field changes shape here; what changes is what lands in them, and
what comicbox writes to other apps' files.

- **ComicInfo `GTIN` is a barcode again.** Comicbox used to dump every
  identifier into it as a comma-joined urn list. Kavita, Komga and Mylar read
  GTIN as an actual barcode, so comicbox was corrupting that field for them. It
  now reads a single value (recording it as `isbn` or `upc` by length) and
  writes back only an `isbn`, `upc` or `gtin` identifier. Files already written
  with urns still read — the urn list is still parsed on the way in. Database
  ids reach ComicInfo through `Web` and the `Notes` urns instead.
- **`MainCharacterOrTeam`** is read as one name, so `protagonist` keeps a comma
  in it (`"Hank McCoy, Beast"`) instead of splitting into two.
- **CoMet `identifier` and `isVersionOf`** are single-valued per their XSD, so
  `reprints` from CoMet holds at most one entry, and CoMet's `identifier` is
  written as one urn (the best-ranked source) rather than a set.
- **ComicInfo `Translator`** now splits on commas like the other seven creator
  tags, so multi-translator books keep every credit.

**Codex impact:** none to the stored shape. Worth knowing if codex compares
comicbox's ComicInfo output against files written by older versions.

### PR 7 — `manga_volume`

New field `comicbox.manga_volume`, a string holding MetronInfo's `MangaVolume`
exactly as the file wrote it. `volume.number` and `volume.number_to` are
unchanged and are still filled in from it — comicbox parses `"3"` and `"1-5"`
for you — but only when the file didn't state a `Series/Volume` of its own.

| Field                                | v3                                                 |
| ------------------------------------ | -------------------------------------------------- |
| `manga_volume`                       | new; verbatim string, may be any text              |
| `volume.number` / `volume.number_to` | unchanged; derived from `manga_volume` when absent |

**This fixes a data-corruption bug worth knowing about.** `MangaVolume` used to
be split into the volume numbers on read and rebuilt from them on write,
unconditionally — so every comic comicbox wrote MetronInfo for came out claiming
a manga volume, western comics included. Any MetronInfo.xml comicbox wrote may
carry a bogus `<MangaVolume>`; it now writes one only when `manga_volume` holds
a value that came from a file.

**Codex impact:** new optional field. Nothing to migrate — v2 never stored the
string, so it cannot be recovered from stored data; it arrives when a MetronInfo
file is next read.

### PR 8 — ComicInfo `AlternateSeries` is an arc, not a reprint

No new fields. Data that used to arrive in `reprints` now arrives in `arcs`.

| ComicInfo tag     | v2                              | v3                   |
| ----------------- | ------------------------------- | -------------------- |
| `AlternateSeries` | `reprints[].series.name`        | `arcs.<name>`        |
| `AlternateNumber` | `reprints[].issue`              | `arcs.<name>.number` |
| `AlternateCount`  | `reprints[].volume.issue_count` | dropped              |

ComicInfo v1.0 had no `StoryArc` — it arrived in v2.0 — so libraries tagged
before then recorded crossovers in these three tags. ComicRack documented them
for exactly that (Civil War, House of M), the Anansi project calls them
"cross-over story arcs", and Komga and Kavita build read lists from
`AlternateSeries` + `AlternateNumber` the same way they do from `StoryArc` +
`StoryArcNumber`. Reading them as reprints put crossover data in the field
meaning "another edition of this book".

Comicbox now **writes** arcs only to `StoryArc`/`StoryArcNumber`, so a file it
touches is migrated to the modern tags. When both tag pairs name the same arc,
`StoryArc` wins.

**Consequence worth knowing:** ComicInfo can no longer carry a reprint at all.
Writing only ComicInfo for a comic whose reprints came from CoMet or MetronInfo
loses them, because ComicInfo has no field for that concept.

**Codex migration:** reprint rows that came from ComicInfo become arc rows.
There is no way to tell them apart after the fact from the stored data alone, so
the practical move is to re-read affected comics rather than migrate.

### PR 9 — reprints keep their name, series gains `alternative_names`

Two concepts MetronInfo keeps in separate tags were both landing in `reprints`.

| Source                    | v2                                                 | v3                                                      |
| ------------------------- | -------------------------------------------------- | ------------------------------------------------------- |
| `Reprints/Reprint`        | `reprints[]` with parsed `series`/`volume`/`issue` | `reprints[].name` verbatim, plus the same parsed fields |
| `Series/AlternativeNames` | appended to `reprints[]`                           | `series.alternative_names[]`                            |

New `series.alternative_names`, a list of `{name, language?, identifiers?}` —
the other names the same series goes by: translations, romanizations, variant
spellings. A reprint means something else entirely: another edition of this
issue's content.

`reprints[].name` is new and is **authoritative**. Comicbox stores what the file
wrote and writes that back. The `series`, `volume` and `issue` fields are still
there and still filled in, read out of the name for convenience, but a reprint
whose name the filename grammar can't model — "Amazing Fantasy #15 (2nd
printing)" — is no longer silently rewritten on the way out.

**Bug this fixes:** `AlternativeNames` were read into `reprints`, and then every
reprint with a series name was written back out to **both** `<Reprints>` and
`<AlternativeNames>`. Each read-write cycle multiplied the entries. MetronInfo
files comicbox has written may carry inflated lists.

Also: a `<AlternativeName>` with no `lang` attribute was dropped on read (it
parses as a bare string, not a mapping). `lang` defaults to `en` in the schema,
so those are legal and common.

**Codex migration:** reprint rows keep working; `name` is additive. Series
alternative names that codex stored as reprints should move, but as with the
ComicInfo arcs, re-reading affected comics is more reliable than guessing which
reprint rows were really alternative names.

### PR 10 — `title` and `stories` derive only when missing

No shape change. `title` is still a string and `stories` still a name-keyed map;
what changes is when comicbox fills one in from the other.

| Comic states | v2 result                                                                             | v3 result                   |
| ------------ | ------------------------------------------------------------------------------------- | --------------------------- |
| stories only | title = stories joined with `; `                                                      | same                        |
| title only   | stories = title split on `;`                                                          | same                        |
| both         | **title overwritten** with the joined stories, and stories gained the title's entries | both kept exactly as stated |

A `title` the source stated is now the title. It used to be replaced by the
joined story names so that MetronInfo, which has no title tag, would beat a
title guessed from the filename — but which source wins is the merge order's
job, and solving it here meant overwriting data a file actually contained.

**Codex impact:** a comic carrying both a title and story names may now show a
different title than before — the one in the file rather than one rebuilt from
its stories. Nothing to migrate.

### v2.0 documents

There is no up-converter. Comicbox reads v3 only, and a v2 document loads with
its renamed and removed fields ignored, because the schemas exclude unknown
fields rather than rejecting them. Such a file silently loses its
`identifier_primary_source`, every `identifiers.*.url`, `credit_primaries`,
`critical_rating` and `alternate_images`, and a `manga` of `YesAndRightToLeft`
fails the enum.

The field tables above are the conversion rules, if codex has comicbox documents
of its own to migrate.

## Adoption checklist

- [ ] Remove any `alternate_images` and `critical_rating` handling.
- [ ] Migrate stored credit-role strings to the canonical Metron vocabulary
      (table in the PR 2 section); keep unknown roles permitted.
- [ ] Migrate stored age ratings to the Metron scale (table in the PR 3
      section); keep unknown ratings permitted.
- [ ] Split any stored `manga` value of `YesAndRightToLeft`; read right-to-left
      from `reading_direction`.
- [ ] Move credit primary flags onto the per-role object (PR 4 section).
- [ ] Split stored identifiers and urls; rename `identifier_primary_source` →
      `primary_id_source` (PR 5 section).
- [ ] Add the optional `manga_volume` field.
- [ ] Add `reprints[].name` and `series.alternative_names` (PR 9 section).
- [ ] Move ComicInfo-sourced reprints to arcs, or re-read those comics (PR 8
      section).
- [ ] Expect a `title` a file states to survive rather than being rebuilt from
      the comic's story names (PR 10 section).
- [ ] Re-run codex's comicbox integration tests against the paired comicbox
      release; comicbox's own `tests/test_codex_api.py` pins the
      `get_internal_metadata()` contract and is the reference for expected
      shape.
