# Comicbox Fields

Most comicbox fields capture concepts from more than one format. These fields
are unique to one format.

## Fields unique to one format

### CoMet

- cover_image
- last_mark
- reading_direction
- rights

### ComicBookInfo

- credits.\<person\>.roles.\<role\>.primary

### ComicInfo

- manga
- monocrhrome
- pages
- protagonist
- review
- series_groups

### MetronInfo

- alternative_issue
- community_rating.rating_count
- primary_id_source
- store_date
- universes

### Filename

- ext
- remainders

## Language tags

`language`, `series.alternative_names[].language` and `reprints[].language` are
BCP 47 language tags like `en`, `fil`, `pt-BR` or `zh-Hant`. The primary
language is the shortest ISO 639 code pycountry knows; the other subtags are
kept and recased per RFC 5646.
