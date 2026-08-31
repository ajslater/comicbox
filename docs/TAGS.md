# 🏷️ Tag Translations

This is a rough table of how Comicbox handles tag translations between popular
comic book metadata formats.

| Comicbox                 | ComicInfo                                                                                | MetronInfo                 | ComicBookInfo                                                             | CoMet             |
| ------------------------ | ---------------------------------------------------------------------------------------- | -------------------------- | ------------------------------------------------------------------------- | ----------------- |
| age_rating               | AgeRating                                                                                | AgeRating                  |                                                                           |
| alternative_issue        |                                                                                          | AlternativeNumber          |                                                                           |
| arcs                     | StoryArc, StoryArcNumber, AlternateSeries and AlternateNumber (read)                     | Arcs                       |
| bookmark                 |                                                                                          |                            |                                                                           | lastMark          |
| characacters             | Characters                                                                               |                            |                                                                           | character         |
| country                  |                                                                                          |                            | country                                                                   |
| credits                  | Writer, Penciller, Inker, Colorist, Letterer, CoverArtist, Editor, Translator, Publisher | Credits                    | colorist, coverDesigner, creator, editor, inker, letter, penciller writer |
| collection_title         |                                                                                          | CollectionTitle            |
| community_rating         | CommunityRating                                                                          | CommunityRating            | rating                                                                    |
| cover_image              |                                                                                          |                            |                                                                           | coverImage        |
| date                     | Year, Month, Day                                                                         | CoverDate, StoreDate       | publicationDay, publicationMonth, publicationYear                         | date              |
| ext                      |
| original_format          |
| genres                   | Genre                                                                                    | Genres                     | genre                                                                     | genre             |
| primary_id_source        |                                                                                          | IDS@primary, URLs@primary  |
| identifiers              | GTIN                                                                                     | IDS, GTIN                  | identifier                                                                |
| urls                     | Web                                                                                      | URLs                       |
| imprint                  | Imprint                                                                                  |                            | Publisher.Imprint                                                         |
| issue                    | Number                                                                                   | Number                     | issue                                                                     | issue             |
| language                 | LanguageISO                                                                              | Series@lang                |                                                                           | language          |
| locations                | Locations                                                                                | Locations                  |
| manga                    | Manga                                                                                    |
| manga_volume             |                                                                                          | MangaVolume                |
| monochrome               | BlackAndWhite                                                                            |
| notes                    | Notes                                                                                    | Notes                      |
| original_format          | Format                                                                                   | Series.Format              |
| page_count               | PageCount                                                                                | PageCount                  |
| pages                    | Pages                                                                                    |                            | pages                                                                     | pages, coverImage |
| publisher                | Publisher                                                                                | Publisher                  | publisher                                                                 | publisher         |
| prices                   |                                                                                          | Prices                     |                                                                           | price             |
| protagonist              | MainCharacterOrTeam                                                                      |
| reading_direction        |                                                                                          |                            |                                                                           | readingDirection  |
| remainders               |
| reprints                 |                                                                                          | Reprints                   | isVersionOf                                                               |
| review                   | Review                                                                                   |
| rights                   |                                                                                          |                            |                                                                           | rights            |
| scan_info                | ScanInformation                                                                          |
| series                   | Series                                                                                   | Series                     | series, numberOfVolumes                                                   | series            |
| series.alternative_names |                                                                                          | Series.AlternativeNames    |
| title                    | Title                                                                                    | Stories                    | title                                                                     | title             |
| series_groups            |
| stories                  | Title                                                                                    | Stories                    | title                                                                     | title             |
| summary                  | Summary                                                                                  | Summary                    | comments                                                                  |
| tagger                   |                                                                                          |                            |                                                                           |
| tags                     | Tags                                                                                     | Tags                       | tags                                                                      |
| teams                    | Teams                                                                                    |
| universes                |                                                                                          | Universes                  |
| updated_at               |                                                                                          | LastModified               | lastModified                                                              |
| volume                   | Volume, Count                                                                            | MangaVolume, Series.Volume | volume, numberOfIssues                                                    | volume            |
