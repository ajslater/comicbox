# MetronInfo 1.2

Generated from
[MetronInfo-v1.2.xsd](https://github.com/ajslater/comicbox/blob/main/schemas/MetronInfo-v1.2.xsd).

The root element is `MetronInfo`, of type [metroninfoType](#metroninfotype).

## Complex Types

### metroninfoType

Child elements, in any order:

| Element             | Type                                        | Occurs | Default   | Notes                  |
| ------------------- | ------------------------------------------- | ------ | --------- | ---------------------- |
| `IDS`               | [idsType](#idstype)                         | 0..1   |           |                        |
| `Publisher`         | [publisherType](#publishertype)             | 0..1   |           |                        |
| `Series`            | [seriesType](#seriestype)                   | 1      |           |                        |
| `MangaVolume`       | `xs:string`                                 | 0..1   |           | This is used for Manga |
| `CollectionTitle`   | `xs:string`                                 | 0..1   |           |                        |
| `Number`            | `xs:string`                                 | 0..1   |           |                        |
| `AlternativeNumber` | `xs:string`                                 | 0..1   |           |                        |
| `Stories`           | [storyType](#storytype)                     | 0..1   |           | Story titles in issue  |
| `Summary`           | `xs:string`                                 | 0..1   |           |                        |
| `Prices`            | [pricesType](#pricestype)                   | 0..1   |           |                        |
| `CoverDate`         | `xs:date`                                   | 0..1   |           |                        |
| `StoreDate`         | `xs:date`                                   | 0..1   |           |                        |
| `PageCount`         | `xs:nonNegativeInteger`                     | 0..1   | `0`       |                        |
| `Notes`             | `xs:string`                                 | 0..1   |           |                        |
| `Genres`            | [genresType](#genrestype)                   | 0..1   |           |                        |
| `Tags`              | [tagsType](#tagstype)                       | 0..1   |           |                        |
| `Arcs`              | [arcsType](#arcstype)                       | 0..1   |           |                        |
| `Characters`        | [charactersType](#characterstype)           | 0..1   |           |                        |
| `Teams`             | [teamsType](#teamstype)                     | 0..1   |           |                        |
| `Universes`         | [universesType](#universestype)             | 0..1   |           |                        |
| `Locations`         | [locationsType](#locationstype)             | 0..1   |           |                        |
| `Reprints`          | [reprintsType](#reprintstype)               | 0..1   |           |                        |
| `GTIN`              | [gtinType](#gtintype)                       | 0..1   |           |                        |
| `AgeRating`         | [ageRatingType](#ageratingtype)             | 0..1   | `Unknown` |                        |
| `CommunityRating`   | [communityRatingType](#communityratingtype) | 0..1   |           |                        |
| `URLs`              | [urlsType](#urlstype)                       | 0..1   |           |                        |
| `Credits`           | [creditsType](#creditstype)                 | 0..1   |           |                        |
| `LastModified`      | `xs:dateTime`                               | 0..1   |           |                        |

### urlsType

Child elements, in this order:

| Element | Type                | Occurs |
| ------- | ------------------- | ------ |
| `URL`   | [urlType](#urltype) | 0..*   |

Rules:

- `count(URL[@primary = true()]) <= 1`

### urlType

Text of type `xs:string`.

Attributes:

| Attribute | Type         | Use      |
| --------- | ------------ | -------- |
| `primary` | `xs:boolean` | optional |

### idsType

Child elements, in this order:

| Element | Type              | Occurs |
| ------- | ----------------- | ------ |
| `ID`    | [idType](#idtype) | 0..*   |

Rules:

- `count(ID[@primary = true()]) <= 1`

### idType

Text of type `xs:string`.

Attributes:

| Attribute | Type                                    | Use      |
| --------- | --------------------------------------- | -------- |
| `source`  | [informationSource](#informationsource) | required |
| `primary` | `xs:boolean`                            | optional |

### storyType

Child elements, in this order:

| Element | Type                          | Occurs |
| ------- | ----------------------------- | ------ |
| `Story` | [resourceType](#resourcetype) | 0..*   |

### resourceType

Base type to add 'id' attribute to the various resources

Text of type `xs:string`.

Attributes:

| Attribute | Type        | Use      |
| --------- | ----------- | -------- |
| `id`      | `xs:string` | optional |

### publisherType

Child elements, in any order:

| Element   | Type                          | Occurs |
| --------- | ----------------------------- | ------ |
| `Name`    | `xs:string`                   | 1      |
| `Imprint` | [resourceType](#resourcetype) | 0..1   |

Attributes:

| Attribute | Type        | Use      |
| --------- | ----------- | -------- |
| `id`      | `xs:string` | optional |

### seriesType

Child elements, in any order:

| Element            | Type                                        | Occurs |
| ------------------ | ------------------------------------------- | ------ |
| `Name`             | `xs:string`                                 | 1      |
| `SortName`         | `xs:string`                                 | 0..1   |
| `Volume`           | `xs:nonNegativeInteger`                     | 0..1   |
| `Format`           | [formatType](#formattype)                   | 0..1   |
| `StartYear`        | `xs:gYear`                                  | 0..1   |
| `EndYear`          | `xs:gYear`                                  | 0..1   |
| `Status`           | [seriesStatusType](#seriesstatustype)       | 0..1   |
| `IssueCount`       | `xs:positiveInteger`                        | 0..1   |
| `VolumeCount`      | `xs:positiveInteger`                        | 0..1   |
| `AlternativeNames` | [alternativeNameType](#alternativenametype) | 0..1   |
| `Summary`          | `xs:string`                                 | 0..1   |

Attributes:

| Attribute | Type                          | Use      | Default |
| --------- | ----------------------------- | -------- | ------- |
| `lang`    | [languageCode](#languagecode) | optional | `en`    |
| `id`      | `xs:string`                   | optional |         |

Rules:

- EndYear can't precede StartYear. replace() strips the optional gYear timezone
  so the years cast to integers.
  `not(StartYear and EndYear) or xs:integer(replace(string(EndYear), '(Z|[+\-]\d{2}:\d{2})$', '')) ge xs:integer(replace(string(StartYear), '(Z|[+\-]\d{2}:\d{2})$', ''))`
- An ongoing series has no EndYear. `not(Status = 'Ongoing' and EndYear)`

### alternativeNameType

Child elements, in this order:

| Element           | Type                  | Occurs |
| ----------------- | --------------------- | ------ |
| `AlternativeName` | [nameType](#nametype) | 0..*   |

### nameType

Alternative Series Name Base type

Text of type `xs:string`.

Attributes:

| Attribute | Type                          | Use      | Default |
| --------- | ----------------------------- | -------- | ------- |
| `id`      | `xs:string`                   | optional |         |
| `lang`    | [languageCode](#languagecode) | optional | `en`    |

### charactersType

Child elements, in this order:

| Element     | Type                          | Occurs |
| ----------- | ----------------------------- | ------ |
| `Character` | [resourceType](#resourcetype) | 0..*   |

### teamsType

Child elements, in this order:

| Element | Type                          | Occurs |
| ------- | ----------------------------- | ------ |
| `Team`  | [resourceType](#resourcetype) | 0..*   |

### locationsType

Child elements, in this order:

| Element    | Type                          | Occurs |
| ---------- | ----------------------------- | ------ |
| `Location` | [resourceType](#resourcetype) | 0..*   |

### tagsType

Child elements, in this order:

| Element | Type                          | Occurs |
| ------- | ----------------------------- | ------ |
| `Tag`   | [resourceType](#resourcetype) | 0..*   |

### reprintsType

Child elements, in this order:

| Element   | Type                          | Occurs |
| --------- | ----------------------------- | ------ |
| `Reprint` | [resourceType](#resourcetype) | 0..*   |

### universesType

Child elements, in this order:

| Element    | Type                          | Occurs |
| ---------- | ----------------------------- | ------ |
| `Universe` | [universeType](#universetype) | 0..*   |

### universeType

Child elements, in any order:

| Element       | Type        | Occurs |
| ------------- | ----------- | ------ |
| `Name`        | `xs:string` | 1      |
| `Designation` | `xs:string` | 0..1   |

Attributes:

| Attribute | Type        | Use      |
| --------- | ----------- | -------- |
| `id`      | `xs:string` | optional |

### arcsType

Child elements, in this order:

| Element | Type                | Occurs |
| ------- | ------------------- | ------ |
| `Arc`   | [arcType](#arctype) | 0..*   |

### arcType

Child elements, in any order:

| Element  | Type                 | Occurs |
| -------- | -------------------- | ------ |
| `Name`   | `xs:string`          | 1      |
| `Number` | `xs:positiveInteger` | 0..1   |

Attributes:

| Attribute | Type        | Use      |
| --------- | ----------- | -------- |
| `id`      | `xs:string` | optional |

### creditsType

Child elements, in this order:

| Element  | Type                      | Occurs |
| -------- | ------------------------- | ------ |
| `Credit` | [creditType](#credittype) | 0..*   |

### roleType

Text of type [roleValues](#rolevalues).

Attributes:

| Attribute | Type        | Use      |
| --------- | ----------- | -------- |
| `id`      | `xs:string` | optional |

### rolesType

Child elements, in this order:

| Element | Type                  | Occurs |
| ------- | --------------------- | ------ |
| `Role`  | [roleType](#roletype) | 0..*   |

### creditType

Child elements, in any order:

| Element   | Type                          | Occurs |
| --------- | ----------------------------- | ------ |
| `Creator` | [resourceType](#resourcetype) | 1      |
| `Roles`   | [rolesType](#rolestype)       | 0..1   |

### genresType

Child elements, in this order:

| Element | Type                          | Occurs |
| ------- | ----------------------------- | ------ |
| `Genre` | [resourceType](#resourcetype) | 0..*   |

### pricesType

Child elements, in this order:

| Element | Type                    | Occurs |
| ------- | ----------------------- | ------ |
| `Price` | [priceType](#pricetype) | 0..*   |

### priceType

Text of type `xs:decimal`.

Attributes:

| Attribute | Type                        | Use      |
| --------- | --------------------------- | -------- |
| `country` | [countryCode](#countrycode) | required |

### gtinType

Child elements, in any order:

| Element | Type         | Occurs |
| ------- | ------------ | ------ |
| `ISBN`  | `xs:anyType` | 0..1   |
| `UPC`   | `xs:anyType` | 0..1   |

### communityRatingType

Child elements, in any order:

| Element         | Type                                    | Occurs |
| --------------- | --------------------------------------- | ------ |
| `AverageRating` | [averageRatingType](#averageratingtype) | 1      |
| `RatingCount`   | `xs:positiveInteger`                    | 0..1   |

## Simple Types

### informationSource

Restricts `xs:string` to:

| Value                   | Notes                                      |
| ----------------------- | ------------------------------------------ |
| `AniList`               |                                            |
| `Comic Vine`            |                                            |
| `Grand Comics Database` |                                            |
| `Kitsu`                 | ID's contain letters, hyphens, and numbers |
| `MangaDex`              | ID's contain letters, hyphens, and numbers |
| `MangaUpdates`          |                                            |
| `Marvel`                |                                            |
| `Metron`                |                                            |
| `MyAnimeList`           |                                            |
| `League of Comic Geeks` |                                            |

### languageCode

BCP 47 language tag (e.g. en, fil, pt-BR, zh-Hant). Case-insensitive.

Restricts `xs:string` to:

- Pattern: `[a-zA-Z]{2,3}(-[a-zA-Z0-9]{1,8})*`

### roleValues

Restricts `xs:string` to:

| Value                    |
| ------------------------ |
| `Writer`                 |
| `Script`                 |
| `Story`                  |
| `Plot`                   |
| `Interviewer`            |
| `Artist`                 |
| `Penciller`              |
| `Breakdowns`             |
| `Illustrator`            |
| `Layouts`                |
| `Inker`                  |
| `Embellisher`            |
| `Finishes`               |
| `Ink Assists`            |
| `Colorist`               |
| `Color Separations`      |
| `Color Assists`          |
| `Color Flats`            |
| `Digital Art Technician` |
| `Gray Tone`              |
| `Letterer`               |
| `Cover`                  |
| `Editor`                 |
| `Consulting Editor`      |
| `Assistant Editor`       |
| `Associate Editor`       |
| `Group Editor`           |
| `Senior Editor`          |
| `Managing Editor`        |
| `Collection Editor`      |
| `Production`             |
| `Designer`               |
| `Logo Design`            |
| `Translator`             |
| `Supervising Editor`     |
| `Executive Editor`       |
| `Editor In Chief`        |
| `President`              |
| `Publisher`              |
| `Chief Creative Officer` |
| `Executive Producer`     |
| `Other`                  |

### countryCode

Restricts `xs:string` to:

- Pattern: `[A-Z][A-Z]`

### formatType

Restricts `xs:string` to:

| Value             | Notes                             |
| ----------------- | --------------------------------- |
| `Annual`          |                                   |
| `Digital Chapter` |                                   |
| `Graphic Novel`   |                                   |
| `Hardcover`       |                                   |
| `Limited Series`  | Used for mini/maxi series         |
| `Omnibus`         |                                   |
| `One-Shot`        |                                   |
| `Single Issue`    | Used for Ongoing/Cancelled series |
| `Trade Paperback` |                                   |

### seriesStatusType

Restricts `xs:string` to:

| Value       |
| ----------- |
| `Cancelled` |
| `Completed` |
| `Hiatus`    |
| `Ongoing`   |

### ageRatingType

There's no governing body for age ratings, so let's use something fairly simple
to cover most cases. It won't be perfect, but adding different values for all
the different ways publishers use them seems unnecessarily difficult. The age
ranges are just suggestions.

Restricts `xs:string` to:

| Value       | Notes                                                                              |
| ----------- | ---------------------------------------------------------------------------------- |
| `Unknown`   |                                                                                    |
| `Everyone`  | Appropriate for readers of all ages.                                               |
| `Teen`      | Appropriate for readers age 12 and older.                                          |
| `Teen Plus` | Appropriate for readers age 15 and older.                                          |
| `Mature`    | Appropriate for readers age 17 and older.                                          |
| `Explicit`  | Contains Gore, Sexually Explicit material that would be more extreme than R rating |
| `Adult`     | Likely pornographic in nature                                                      |

### averageRatingType

Restricts `xs:decimal` to:

- Minimum: `0`
- Maximum: `5.0`
