# 🏷️ Tag Translations

This is a rough table of how Comicbox handles tag translations between popular
comic book metadata formats.

| Comicbox                  | ComicInfo                                                                                | MetronInfo                        | ComicBookInfo                                                             | CoMet             |
| ------------------------- | ---------------------------------------------------------------------------------------- | --------------------------------- | ------------------------------------------------------------------------- | ----------------- |
| age_rating                | AgeRating                                                                                | AgeRating                         |                                                                           |
| alternate_images          |                                                                                          |                                   |                                                                           |
| arcs                      | StoryArc, StoryArcNumbers                                                                |
| bookmark                  |                                                                                          |                                   |                                                                           | lastMark          |
| characacters              | Characters                                                                               |                                   |                                                                           | character         |
| country                   |                                                                                          |                                   | country                                                                   |
| credits                   | Writer, Penciller, Inker, Colorist, Letterer, CoverArtist, Editor, Translator, Publisher | Credits                           | colorist, coverDesigner, creator, editor, inker, letter, penciller writer |
| credit_primaries          |
| collection_title          |                                                                                          | CollectionTitle                   |
| cover_image               |                                                                                          |                                   |                                                                           | coverImage        |
| critical_rating           | CommunityRating                                                                          |                                   | rating                                                                    | rating            |
| date                      | Year, Month, Day                                                                         | CoverDate, StoreDate              | publicationDay, publicationMonth, publicationYear                         | date              |
| ext                       |
| original_format           |
| genres                    | Genre                                                                                    | Genres                            | genre                                                                     | genre             |
| identifier_primary_source |
| identifiers               | Web, GTIN                                                                                | IDS, GTIN, URLs                   | identifier                                                                |
| imprint                   | Imprint                                                                                  |                                   | Publisher.Imprint                                                         |
| issue                     | Number                                                                                   | Number                            | issue                                                                     | issue             |
| language                  | LanguageISO                                                                              | Series@lang                       |                                                                           | language          |
| locations                 | Locations                                                                                | Locations                         |
| manga                     | Manga                                                                                    |
| monochrome                | BlackAndWhite                                                                            |
| notes                     | Notes                                                                                    | Notes                             |
| original_format           | Format                                                                                   | Series.Format                     |
| page_count                | PageCount                                                                                | PageCount                         |
| pages                     | Pages                                                                                    |                                   | pages                                                                     | pages, coverImage |
| publisher                 | Publisher                                                                                | Publisher                         | publisher                                                                 | publisher         |
| prices                    |                                                                                          | Prices                            |                                                                           | price             |
| protagonist               | MainCharacterOrTeam                                                                      |
| reading_direction         |                                                                                          |                                   |                                                                           | readingDirection  |
| remainders                |
| reprints                  | AlternateSeries, AlternateCount, AlternateNumber                                         | Reprints, Series.AlternativeNames | isVersionOf                                                               |
| review                    | Review                                                                                   |
| rights                    |                                                                                          |                                   |                                                                           | rights            |
| scan_info                 | ScanInformation                                                                          |
| series                    | Series                                                                                   | Series                            | series, numberOfVolumes                                                   | series            |
| title                     | Title                                                                                    | Stories                           | title                                                                     | title             |
| series_groups             |
| stories                   | Title                                                                                    | Stories                           | title                                                                     | title             |
| summary                   | Summary                                                                                  | Summary                           | comments                                                                  |
| tagger                    |                                                                                          |                                   |                                                                           |
| tags                      | Tags                                                                                     | Tags                              | tags                                                                      |
| teams                     | Teams                                                                                    |
| universes                 |                                                                                          | Universes                         |
| updated_at                |                                                                                          | LastModified                      | lastModified                                                              |
| volume                    | Volume, Count                                                                            | MangaVolume, Series.Volume        | volume, numberOfIssues                                                    | volume            |
