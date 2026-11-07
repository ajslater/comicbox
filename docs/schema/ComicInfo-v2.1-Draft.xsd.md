# ComicInfo 2.1 Draft

Generated from
[ComicInfo-v2.1-Draft.xsd](https://github.com/ajslater/comicbox/blob/main/schemas/ComicInfo-v2.1-Draft.xsd).

The root element is `ComicInfo`, of type [ComicInfo](#comicinfo).

## Complex Types

### ComicInfo

Child elements, in this order:

| Element               | Type                                          | Occurs | Default   |
| --------------------- | --------------------------------------------- | ------ | --------- |
| `Title`               | `xs:string`                                   | 0..1   | `""`      |
| `Series`              | `xs:string`                                   | 0..1   | `""`      |
| `Number`              | `xs:string`                                   | 0..1   | `""`      |
| `Count`               | `xs:int`                                      | 0..1   | `-1`      |
| `Volume`              | `xs:int`                                      | 0..1   | `-1`      |
| `AlternateSeries`     | `xs:string`                                   | 0..1   | `""`      |
| `AlternateNumber`     | `xs:string`                                   | 0..1   | `""`      |
| `AlternateCount`      | `xs:int`                                      | 0..1   | `-1`      |
| `Summary`             | `xs:string`                                   | 0..1   | `""`      |
| `Notes`               | `xs:string`                                   | 0..1   | `""`      |
| `Year`                | `xs:int`                                      | 0..1   | `-1`      |
| `Month`               | `xs:int`                                      | 0..1   | `-1`      |
| `Day`                 | `xs:int`                                      | 0..1   | `-1`      |
| `Writer`              | `xs:string`                                   | 0..1   | `""`      |
| `Penciller`           | `xs:string`                                   | 0..1   | `""`      |
| `Inker`               | `xs:string`                                   | 0..1   | `""`      |
| `Colorist`            | `xs:string`                                   | 0..1   | `""`      |
| `Letterer`            | `xs:string`                                   | 0..1   | `""`      |
| `CoverArtist`         | `xs:string`                                   | 0..1   | `""`      |
| `Editor`              | `xs:string`                                   | 0..1   | `""`      |
| `Translator`          | `xs:string`                                   | 0..1   | `""`      |
| `Publisher`           | `xs:string`                                   | 0..1   | `""`      |
| `Imprint`             | `xs:string`                                   | 0..1   | `""`      |
| `Genre`               | `xs:string`                                   | 0..1   | `""`      |
| `Tags`                | `xs:string`                                   | 0..1   | `""`      |
| `Web`                 | `xs:string`                                   | 0..1   | `""`      |
| `PageCount`           | `xs:int`                                      | 0..1   | `0`       |
| `LanguageISO`         | `xs:string`                                   | 0..1   | `""`      |
| `Format`              | `xs:string`                                   | 0..1   | `""`      |
| `BlackAndWhite`       | [YesNo](#yesno)                               | 0..1   | `Unknown` |
| `Manga`               | [Manga](#manga)                               | 0..1   | `Unknown` |
| `Characters`          | `xs:string`                                   | 0..1   | `""`      |
| `Teams`               | `xs:string`                                   | 0..1   | `""`      |
| `Locations`           | `xs:string`                                   | 0..1   | `""`      |
| `ScanInformation`     | `xs:string`                                   | 0..1   | `""`      |
| `StoryArc`            | `xs:string`                                   | 0..1   | `""`      |
| `StoryArcNumber`      | `xs:string`                                   | 0..1   | `""`      |
| `SeriesGroup`         | `xs:string`                                   | 0..1   | `""`      |
| `AgeRating`           | [AgeRating](#agerating)                       | 0..1   | `Unknown` |
| `Pages`               | [ArrayOfComicPageInfo](#arrayofcomicpageinfo) | 0..1   |           |
| `CommunityRating`     | [Rating](#rating)                             | 0..1   |           |
| `MainCharacterOrTeam` | `xs:string`                                   | 0..1   | `""`      |
| `Review`              | `xs:string`                                   | 0..1   | `""`      |
| `GTIN`                | `xs:string`                                   | 0..1   | `""`      |

### ArrayOfComicPageInfo

Child elements, in this order:

| Element | Type                            | Occurs |
| ------- | ------------------------------- | ------ |
| `Page`  | [ComicPageInfo](#comicpageinfo) | 0..*   |

### ComicPageInfo

Attributes:

| Attribute     | Type                            | Use      | Default |
| ------------- | ------------------------------- | -------- | ------- |
| `Image`       | `xs:int`                        | required |         |
| `Type`        | [ComicPageType](#comicpagetype) | optional | `Story` |
| `DoublePage`  | `xs:boolean`                    | optional | `false` |
| `ImageSize`   | `xs:long`                       | optional | `0`     |
| `Key`         | `xs:string`                     | optional | `""`    |
| `Bookmark`    | `xs:string`                     | optional | `""`    |
| `ImageWidth`  | `xs:int`                        | optional | `-1`    |
| `ImageHeight` | `xs:int`                        | optional | `-1`    |

## Simple Types

### YesNo

Restricts `xs:string` to:

| Value     |
| --------- |
| `Unknown` |
| `No`      |
| `Yes`     |

### Manga

Restricts `xs:string` to:

| Value               |
| ------------------- |
| `Unknown`           |
| `No`                |
| `Yes`               |
| `YesAndRightToLeft` |

### Rating

Restricts `xs:decimal` to:

- Minimum: `0`
- Maximum: `5`
- Fraction digits: `1`

### AgeRating

Restricts `xs:string` to:

| Value             |
| ----------------- |
| `Unknown`         |
| `Adults Only 18+` |
| `Early Childhood` |
| `Everyone`        |
| `Everyone 10+`    |
| `G`               |
| `Kids to Adults`  |
| `M`               |
| `MA15+`           |
| `Mature 17+`      |
| `PG`              |
| `R18+`            |
| `Rating Pending`  |
| `Teen`            |
| `X18+`            |

### ComicPageType

A space-separated list of `xs:string` values:

| Value           |
| --------------- |
| `FrontCover`    |
| `InnerCover`    |
| `Roundup`       |
| `Story`         |
| `Advertisement` |
| `Editorial`     |
| `Letters`       |
| `Preview`       |
| `BackCover`     |
| `Other`         |
| `Deleted`       |
