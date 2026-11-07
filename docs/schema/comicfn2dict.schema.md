# Filename

Generated from
[comicfn2dict.schema.json](https://github.com/ajslater/comicfn2dict/blob/main/comicfn2dict/schemas/comicfn2dict.schema.json)
in comicfn2dict 1.1.0.

_The metadata dict that `comicfn2dict()` parses from a comic filename and
`dict2comicfn()` writes a filename from. Every key is optional: `comicfn2dict()`
leaves a key out rather than return it empty, and `dict2comicfn()` skips a key
that is missing or empty._

## Properties

- <a id="properties/series"></a>**`series`** _(string)_: The series name: the
  first run of free text. Underscores become spaces, dots between letters become
  spaces (`Z.O.O.` becomes `Z O O`), and a trailing credit of three or more
  words after `by` is dropped. Length must be at least 1.
- <a id="properties/volume"></a>**`volume`** _(string)_: The volume number, from
  `v1`, `Vol. 1`, `Volume 1`, `1 (of 3)` or `Book One`, which becomes `1`. When
  a filename holds two parenthesized years, the first is the volume. Must match
  pattern: `^[0-9]+$`
  ([Test](https://regexr.com/?expression=%5E%5B0-9%5D%2B%24)).
- <a id="properties/volume_count"></a>**`volume_count`** _(string)_: The number
  of volumes, from `(of N)` after the volume. Must match pattern: `^[0-9]+$`
  ([Test](https://regexr.com/?expression=%5E%5B0-9%5D%2B%24)).
- <a id="properties/issue"></a>**`issue`** _(string)_: The issue number as
  written, with any leading zeros and suffix: `001`, `1.1`, `½`, `27AU`,
  `54.LR`. It is read from `#N`, `N (of M)`, the word `issue`, or a number that
  starts or ends a run of text. A `#` before letters gives a letter issue such
  as `Omega`. With no issue but a volume, the volume is copied here.
  `dict2comicfn()` pads the leading digits to three, after any `-` sign, so `-1`
  is written `#-001`, and writes a letter issue unpadded, as `#Omega`. Length
  must be at least 1.
- <a id="properties/issue_count"></a>**`issue_count`** _(string)_: The number of
  issues, from `(of N)` after the issue. Must match pattern: `^[0-9]+$`
  ([Test](https://regexr.com/?expression=%5E%5B0-9%5D%2B%24)).
- <a id="properties/year"></a>**`year`** _(string)_: The year, from a
  parenthesized year such as `(2020)`, a date, or a year that ends a run of text
  when another run follows it. Must match pattern: `^[12][0-9]{3}$`
  ([Test](https://regexr.com/?expression=%5E%5B12%5D%5B0-9%5D%7B3%7D%24)).
- <a id="properties/month"></a>**`month`** _(string)_: The month number, from 1
  to 12. A numeric month is kept as written. A month name, full or abbreviated,
  becomes its two-digit number: `Dec` becomes `12`. Of a range such as
  `Jan-Feb`, only the first month is kept. `dict2comicfn()` writes a month only
  from 1 to 12: as given after a year, as in `(2020-12)`, and by its name with
  no year, as in `(Dec)`. It leaves any other month out, with its day. Must
  match pattern: `^(0?[1-9]|1[0-2])$`
  ([Test](https://regexr.com/?expression=%5E%280%3F%5B1-9%5D%7C1%5B0-2%5D%29%24)).
- <a id="properties/day"></a>**`day`** _(string)_: The day of the month as
  written, from 1 to 31, from a date such as `2020-12-31`, `Dec 31, 2020` or
  `(Dec-31)`. `dict2comicfn()` writes a day only with a month. Must match
  pattern: `^(0?[1-9]|[12][0-9]|3[01])$`
  ([Test](https://regexr.com/?expression=%5E%280%3F%5B1-9%5D%7C%5B12%5D%5B0-9%5D%7C3%5B01%5D%29%24)).
- <a id="properties/title"></a>**`title`** _(string)_: The issue title: free
  text after the series and an issue, volume, year or month, and before the
  original format and scan info. It is also read from the text after a lone
  spaced dash, as in `Series - Title`, from a single Title Case parenthesized
  group, or from `Book N`. Length must be at least 1.
- <a id="properties/publisher"></a>**`publisher`** _(string)_: A publisher that
  comicfn2dict knows by name, as written in the filename: `DC`, `Marvel`,
  `Image`. Length must be at least 1.
- <a id="properties/original_format"></a>**`original_format`** _(string)_: A
  publication format that comicfn2dict knows by name, as written in the
  filename: `TPB`, `Digital`, `HC`. Length must be at least 1.
- <a id="properties/scan_info"></a>**`scan_info`** _(string)_: The scanner or
  release group: the parenthesized group after the original format, as in
  `(Digital) (Empire)`, or the text after a `-` or `:` inside the format's
  group, as in `(Digital-Empire)` or `(Digital: Empire)`. A parenthesized group
  right after `(c2c)` is the scan info, as in `(c2c) (Scanner-DCP)`. A bare
  `c2c` fills it when nothing else does. Length must be at least 1.
- <a id="properties/remainders"></a>**`remainders`**: Text that fits no other
  key, as a tuple of strings: leftover runs of text first, then the leftover
  parenthesized and bracketed groups, kept together as one string in
  parentheses, so `[5 covers]` becomes `(5 covers)`. `dict2comicfn()` writes the
  remainders in one bracketed group at the end of the name, joined with spaces;
  that group reads back as one string, as written. `dict2comicfn()` also takes a
  single string; `comicfn2dict()` always returns a tuple.
    - **Any of**
        - <a id="properties/remainders/anyOf/0"></a>_array_: Length must be at
          least 1.
            - <a id="properties/remainders/anyOf/0/items"></a>**Items**
              _(string)_: Length must be at least 1.
        - <a id="properties/remainders/anyOf/1"></a>_string_: Length must be at
          least 1.
- <a id="properties/ext"></a>**`ext`** _(string)_: The file extension, without
  its dot: `cbz`, `cbr`, `pdf`. `dict2comicfn()` writes `cbz` when the key is
  missing or empty. Length must be at least 1.
- <a id="properties/date"></a>**`date`** _(string, write-only)_: Read by
  `dict2comicfn()` only; `comicfn2dict()` never returns it. Text written as the
  date in place of the one built from year, month and day. Length must be at
  least 1.

## Examples

```json
{
    "series": "Conan the Barbarian",
    "issue": "001",
    "year": "2025",
    "title": "Scourge of the Serpent",
    "original_format": "Digital",
    "scan_info": "Mephisto-Empire",
    "remainders": ["(5 covers)"],
    "ext": "cbz"
}
```

## Keys comicbox keeps

Comicbox reads these keys from a filename into its own fields, and writes them
back.

| comicfn2dict key  | comicbox field        |
| ----------------- | --------------------- |
| `day`             | `date.day`            |
| `ext`             | `ext`                 |
| `issue`           | `issue.name`          |
| `issue_count`     | `volume.issue_count`  |
| `month`           | `date.month`          |
| `original_format` | `original_format`     |
| `remainders`      | `remainders`          |
| `scan_info`       | `scan_info`           |
| `series`          | `series.name`         |
| `title`           | `title`               |
| `volume`          | `volume.number`       |
| `volume_count`    | `series.volume_count` |
| `year`            | `date.year`           |

It reads `publisher` into `publisher.name` but never writes it into a filename.
