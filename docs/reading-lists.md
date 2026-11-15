# 📚 Reading Lists

A reading list is a set of comics in reading order: an event, a story arc, a
character's history. Comicbox reads them from files and from comics' own arc
tags, combines lists that describe the same order, and writes them back out.

## Formats

| Format                 | Token      | Suffix  | Read | Write | Validated against                                                |
| ---------------------- | ---------- | ------- | ---- | ----- | ---------------------------------------------------------------- |
| ComicRack reading list | `cbl`      | `.cbl`  | ✓    | ✓     | nothing: the dialect has no schema                               |
| json-cbl 1.0           | `json-cbl` | `.json` | ✓    | ✓     | the [json-cbl 1.0 schema](schema/json-cbl-v1.0.schema.md)        |
| Comicbox YAML          | `yaml`     | `.yaml` | ✓    | ✓     | the [Reading List 1.0 schema](schema/reading-list-v1.0/index.md) |
| Comicbox JSON          | `json`     | `.json` | ✓    | ✓     | the [Reading List 1.0 schema](schema/reading-list-v1.0/index.md) |

The format is detected by content, not file name: an XML root of `ReadingList`
is CBL, JSON with `fileDetails` and `issueList` is json-cbl, and a
`reading_list` root is comicbox's own.

Comicbox YAML and JSON carry everything. The other formats lose what they have
no place for, and comicbox says what before it writes:

- **CBL** keeps the name, start year, one curator and, per issue, the series,
  number, volume, year, and ComicVine and Metron ids. It loses the description,
  type, years beyond the start, chaining to other lists, tags, notes, entry
  types, full dates and other databases' ids. Its `Volume` holds a series start
  year in community files and a volume number in ComicRack's own, so a `Volume`
  between 1900 and next year is read as both.
- **json-cbl** requires a series start year and a full cover date on every
  issue. A cover date is made from the year and month when that is all there is;
  an issue without a start year or a year is left out. An id is written only
  when both its series and issue ids are known.

CBL is read tolerantly: a `<Book>` without a series or number is skipped with a
warning and the rest of the file loads. A ComicRack smart list, whose
`<Matchers>` select comics rather than list them, is refused.

The json-cbl schema is vendored byte for byte from
[json-cbl-standard](https://github.com/ComicReadingLists/json-cbl-standard),
`schema/1.0/comic-reading-list.schema.json` at commit `dea268c` (2024-09-03).

## Command line

`comicbox readinglist`, or `comicbox rl` for short:

```sh
# Print each list as a table, with any warnings.
comicbox rl print "Civil War.cbl"

# Check files against their format's schema.
comicbox rl validate "Civil War.cbl" civil-war.json

# Write a json-cbl copy beside each input, or into a directory.
comicbox rl convert --to json-cbl "Civil War.cbl"
comicbox rl convert --to yaml -o lists/ *.cbl

# Combine lists of one event, the primary first, and print the report.
comicbox rl combine -o civil-war.yaml cbro.cbl locg.cbl

# Say whether two lists are the same list.
comicbox rl compare cbro.cbl locg.cbl

# Write one list per story arc the comics in a directory are tagged with.
comicbox rl from-arcs -o lists/ ~/Comics/Marvel

# Show which of a list's issues a directory has, and which are missing.
comicbox rl match civil-war.yaml ~/Comics/Marvel

# Show how tagging those comics with the list's arc would change them,
# then do it, writing ComicInfo.xml.
comicbox rl write-arcs -w cix civil-war.yaml ~/Comics/Marvel
comicbox rl write-arcs --apply -w cix civil-war.yaml ~/Comics/Marvel
```

`--to` takes a format token from the table above; the default is `yaml`.
`combine` and `fetch` write to stdout without `-o`. stdout only ever holds the
list or table asked for: warnings, what a format loses, the combine report,
fetch progress and log lines go to stderr. A command exits 1 when any file or
fetch fails, and 130 when a fetch is cancelled.

Nothing is written over an existing file unless `--overwrite` is given to
`convert`, `combine`, `from-arcs` or `fetch`, and nothing is ever written over
an input. `convert` checks every destination before it writes any, so two inputs
that would make one file, or a file that would replace an input, write nothing.

A comic file named `readinglist` or `rl` has to be given to comicbox as
`./readinglist` or `./rl`.

## Online sources

Lists can be fetched from Metron, from the DieselTech catalog of ComicRack lists
on GitHub, and from any URL:

```sh
# Search Metron's reading lists by name, then fetch one by its id.
comicbox rl search metron civil war
comicbox rl fetch metron:123 -o civil-war.yaml

# A Metron story arc, as an unordered list.
comicbox rl fetch metron-arc:456

# Search the catalog's paths, then fetch one by its path.
comicbox rl search catalog civil war official
comicbox rl fetch "catalog:Marvel/Events/Official/[Marvel] (2006-02) Civil War (Official).cbl"

# A list anywhere on the web, in any format comicbox reads.
comicbox rl fetch --to json-cbl -o civil-war.json https://example.org/civil-war.cbl
```

| Source              | `fetch` takes   | Needs              |
| ------------------- | --------------- | ------------------ |
| Metron reading list | `metron:ID`     | a Metron API token |
| Metron story arc    | `metron-arc:ID` | a Metron API token |
| DieselTech catalog  | `catalog:PATH`  | nothing            |
| A URL               | `http(s)://...` | nothing            |

A fetched list goes through the same read as a file, so its warnings say what it
dropped, and its source records where it came from: the Metron id, the catalog
path and blob sha, or the URL and its ETag.

### Metron

Give the token with `--auth metron:TOKEN`, `online.auth.metron.key` in the
config, or `COMICBOX_ONLINE__AUTH__METRON__KEY` in the environment, as for
tagging. Reading lists share tagging's rate limit and response cache for the
token, so a fetch and a tagging run queue behind one another, and fetching a
list again within the cache lifetime makes no request.

- **A reading list** keeps Metron's order, its curator (`cbro`, `cmro`, `mg` and
  so on), the lists before and after it, and each issue's Metron, Comic Vine and
  Grand Comics Database ids. A private list is marked `private`.
- **A story arc** has no order of its own, so it is an unordered story list.
  Metron lists an arc's issues with their Metron ids only. When the arc names
  its Comic Vine arc, the list points at it too.

Metron sends a list's issues 100 to a page, the page size in Metron's server
source (not yet checked against a live response), at no fewer than 20 requests a
minute. A 3,000-issue list is 30 pages, about a minute and a half when nothing
else is using the token, and longer during a tagging run. Each page prints its
progress. Ctrl-C stops the fetch before its next request, which can take up to a
minute when the rate limit is spent; a second Ctrl-C quits at once.

### The DieselTech catalog

[DieselTech/CBL-ReadingLists](https://github.com/DieselTech/CBL-ReadingLists)
holds about 1,700 ComicRack lists and no index, so comicbox builds one from a
single call to GitHub's API and caches it in the online cache directory for four
hours. After that it sends GitHub the index's ETag and downloads the index again
only if it changed. GitHub allows 60 API calls an hour without a login; list
downloads are not counted. `--cache off` keeps no index and `--cache refresh`
checks GitHub now.

Each list's curator comes from its file name, such as `(WEB-CBRO)`, `(MG)` or
`(LoCG)`, or from a folder named after its site. Paths there change: comicbox
remembers each list's blob sha, and when a path is gone it fetches the list with
the same sha instead.

### URLs

Any http or https URL, redirects included, in any format above. The format is
detected from the content. A download is read in gzip or deflate, never past
`readinglists.max_download_bytes` once inflated, and within two minutes.

A user name and password in the URL, as in `https://user:pass@host/list.cbl`,
are sent with the request and never recorded on the list or printed. The query
string is kept, because it is part of the address, so a token there is recorded
with the list. Any host is fetched, your own network's included.

### Settings

```yaml
readinglists:
    catalog_repo: DieselTech/CBL-ReadingLists # A fork or mirror works too.
    catalog_ref: main # A branch, tag or commit.
    catalog_ttl: 4h # How long the catalog index is kept.
    max_download_bytes: 16777216 # The largest list or index fetched.
```

### Whose lists these are

Reading lists are their curators' work, and the DieselTech repository has no
license. Comicbox fetches lists only when asked and ships none. Every fetched
list records its curator on its source, and `convert` and `combine` carry it
through, so a list you write out still says whose it was. Share a link to a
list, not a copy of it.

## Combining

`combine` takes lists in rank order, the first being primary, and returns one
list and a report. It is pure: no files, no network.

**What it does:**

- **Matches issues by id, then by name.** Two rows are the same issue when they
  share an issue id from the same database, or the same series name, start year
  (or volume), issue number and suffix, or, weakest of all, the same series
  name, cover year, issue number and suffix. Stronger matches are made first.
  Matches chain: a ComicVine id joining A and B and a Metron id joining B and C
  put all three together.
- **Keeps the primary order.** The first ordered list is the backbone and none
  of its entries ever moves. An issue only another list has goes after the
  nearest entry the two lists agree on. A list marked `ordered: false`, such as
  one built from tags, places its new issues by cover date.
- **Unions the ids.** Each entry gets every database's id from every list;
  everything else comes from the first list that has it.
- **Reports what disagreed.** Order disagreements, two different ids from one
  database for one issue (one of the lists is wrong), every join made on a name
  alone, the kind most likely to be wrong, and an id left on two entries: when
  one list gives an issue twice with a different id each time, its rows cannot
  both join another list's one row.
- **Lines up repeated issues.** A list may read an issue twice; the first time
  lines up with the first time in another list, the second with the second.

**What it does not do:**

- It does not guess past the cover year. An entry with no id and no start year
  or volume matches on its series, issue and cover year, so a CBL row with a
  `Year` and no `Volume` matches its own copy and a row that has the start year.
  Two volumes of one title are told apart only when their issues' cover years
  differ. An entry with no cover year either matches nothing, because a series
  name and number alone match every volume of a long-running title.
- It does not reorder the primary list, even where another list disagrees. To
  keep an order you edited, pass it first.
- It does not decide that two lists describe the same order. That is what
  `compare` is for.
- It does not fix bad ids. It reports them and keeps the primary's.

The same lists in the same order always give the same result. Combining a list
with itself returns it unchanged when every entry has a key; an entry without
one matches nothing, not even its own copy, so it comes out twice. `combine` and
`compare` say how many entries of each input have no key.

## Comparing

`compare` measures how much two lists share and whether their orders agree, and
gives a verdict:

| Verdict   | Meaning                                                             |
| --------- | ------------------------------------------------------------------- |
| same      | Each holds most of the other and the orders agree. Safe to combine. |
| variant   | Each holds most of the other in a different order: two curators.    |
| subset    | One holds most of the other, as tags do a curated list.             |
| unrelated | Little in common.                                                   |

"Most" is three quarters, and orders agree when 90% of the shared issues are in
the same order; both were set from pairs of real lists of the same events. When
either list is marked `ordered: false` its order means nothing, so the verdict
rests on the shared issues alone and the order agreement shows as `n/a`.

## Story arcs

A comic's `arcs` tag is a per-comic view of list membership. `from-arcs`, and
`reading_lists_from_comics` in the API, build one list per arc a set of comics
carries, ordered by arc number. A list is `ordered` only when every comic has
its own number. Each list remembers the arc's Metron and ComicVine ids, so the
full arc can be fetched later. `arc_patch` is the reverse: the tag that adds a
comic to a list.

## Matching a list against your comics

`match` reads every comic under a directory and finds each of a list's issues
among them, in two passes:

1. Every comic that shares a key with an entry: an issue id from the same
   database, the series name, start year or volume, and issue number, or the
   series name, cover year and issue number. Every copy of an issue is found.
2. For each entry the first pass did not find, variants of its series name,
   among the comics no entry found in the first pass: the name without a
   trailing year or volume in parentheses (`Batman (2016)`, `X-Men (Vol. 2)`),
   without a leading article (`The Amazing Spider-Man`), and without a reprint
   suffix such as TPB or Omnibus. A year or volume is never added, so `Iron Man`
   is not the series `Iron Man 2020`. When a variant finds comics of more than
   one series, the cover year picks the series.

A comic is never matched to an entry when both carry an id from one database and
the ids differ, or both have cover years more than a year apart. An entry with
no id, start year, volume or cover year matches nothing, as in `combine`.
`match` prints each entry with each comic that is it on a row of its own, and
how it matched (`id`, `name`, `name-year` or `variant`), or `missing`; a comic
with a tag file comicbox could not read is marked. The count goes to stderr.
Linked directories are not searched, as with comicbox's `--recurse`, and a
directory that cannot be read is a warning: the command then exits 1.

`write-arcs` tags each comic matched by id or name with the list's name as a
story arc, numbered by its place when the list is ordered. `--variants` also
tags the comics found only by a name variant. It needs `-w` with the tag formats
to write, as `comicbox -w` takes them, and writes nothing without `--apply`: by
default it shows each comic's change. A `-w` format that cannot hold the arc
refuses the run before any comic is read: ComicBookInfo has no arcs, and
ComicInfo splits a name with a comma in it into two arcs.

The arc is merged into each comic's tags, whatever `write.merge_mode` says, and
the comic is read back to check that it holds the arc. A comic that already has
the arc with that number is left alone, and one with another number is
renumbered. A comic with a tag file comicbox could not read is listed and not
written, and a file found under two names, through a symbolic or hard link, is
written once. With `general.dry_run` set in the config, `--apply` is a dry run
and says so. A comic that is not written for any reason but having the arc makes
the command exit 1, and the rest are still written. Ctrl-C stops before the
writes not yet started and lets those under way finish, however often it is
pressed. CBR, CBT and CB7 files are converted to CBZ when written, as with any
comicbox write.

## Python API

Everything is in `comicbox.readinglists`:

```python
from comicbox.readinglists import combine, compare, dumps, load, lost_fields

primary = load("cbro.cbl")
other = load("locg.cbl")
result = combine([primary.reading_list, other.reading_list])
print(lost_fields(result.reading_list, "json-cbl"))
text = dumps(result.reading_list, "json-cbl")
```

`load` and `loads` return the list, its format and the warnings the read
produced; the library returns warnings rather than logging them.
`name_variants(entry)` gives the series names `match` tries, normalized, so a
caller matching a list against its own database tries the same ones. The value
passed around is the mapping under `reading_list`. The
[Reading List 1.0 schema](schema/reading-list-v1.0/index.md) describes it.

`ReadingListSession` fetches. It takes the same `OnlineCredentials` as
`OnlineSession`, or reads them from the config, and reports progress as
`ReadingListFetchStarted`, `ReadingListFetchProgress` and
`ReadingListFetchFinished` events:

```python
from comicbox.readinglists import ReadingListSession

with ReadingListSession(on_event=print) as session:
    for found in session.search_metron(name="civil war"):
        print(found.id, found.name, found.curator)
    result = session.fetch_metron_list(123)
    for entry in session.search_catalog("civil war official"):
        catalog_list = session.fetch_catalog(entry.path, sha=entry.sha)
```

A list fetched from Metron has no `fmt`: it was built from records, not read
from a document. `fetch_metron_list` and `fetch_metron_arc` take
`if_modified_since` and return `None`, having fetched no items, when the list
has not changed. `cancel()`, from any thread, stops a fetch before its next
request with `OnlineLookupAbortedError`. A fetch that fails raises
`ReadingListFetchError`.
