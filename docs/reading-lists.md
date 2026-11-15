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
```

`--to` takes a format token from the table above; the default is `yaml`.
`combine` writes to stdout without `-o`, and its report goes to stderr. A
command exits 1 when any file fails.

A comic file named `readinglist` or `rl` has to be given to comicbox as
`./readinglist` or `./rl`.

## Combining

`combine` takes lists in rank order, the first being primary, and returns one
list and a report. It is pure: no files, no network.

**What it does:**

- **Matches issues by id, then by name.** Two rows are the same issue when they
  share an issue id from the same database, or the same series name, start year
  (or volume), issue number and suffix. Matches chain: a ComicVine id joining A
  and B and a Metron id joining B and C put all three together.
- **Keeps the primary order.** The first ordered list is the backbone and none
  of its entries ever moves. An issue only another list has goes after the
  nearest entry the two lists agree on. A list marked `ordered: false`, such as
  one built from tags, places its new issues by cover date.
- **Unions the ids.** Each entry gets every database's id from every list;
  everything else comes from the first list that has it.
- **Reports what disagreed.** Order disagreements, two different ids from one
  database for one issue (one of the lists is wrong), and every join made on a
  name alone, the kind most likely to be wrong.
- **Lines up repeated issues.** A list may read an issue twice; the first time
  lines up with the first time in another list, the second with the second.

**What it does not do:**

- It does not guess. An entry with no id and no start year or volume never
  matches anything, because a series name and number alone match every volume of
  a long-running title.
- It does not reorder the primary list, even where another list disagrees. To
  keep an order you edited, pass it first.
- It does not decide that two lists describe the same order. That is what
  `compare` is for.
- It does not fix bad ids. It reports them and keeps the primary's.

The same lists in the same order always give the same result, and combining a
list with itself returns it unchanged.

## Comparing

`compare` measures how much two lists share and whether their orders agree, and
gives a verdict:

| Verdict   | Meaning                                                             |
| --------- | ------------------------------------------------------------------- |
| same      | Each holds most of the other and the orders agree. Safe to combine. |
| variant   | Each holds most of the other in a different order: two curators.    |
| subset    | One holds most of the other, as tags do a curated list.             |
| unrelated | Little in common.                                                   |

The thresholds were set from pairs of real lists of the same events.

## Story arcs

A comic's `arcs` tag is a per-comic view of list membership. `from-arcs`, and
`reading_lists_from_comics` in the API, build one list per arc a set of comics
carries, ordered by arc number. A list is `ordered` only when every comic has
its own number. Each list remembers the arc's Metron and ComicVine ids, so the
full arc can be fetched later. `arc_patch` is the reverse: the tag that adds a
comic to a list.

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
produced; the library returns warnings rather than logging them. The value
passed around is the mapping under `reading_list`. The
[Reading List 1.0 schema](schema/reading-list-v1.0/index.md) describes it.
