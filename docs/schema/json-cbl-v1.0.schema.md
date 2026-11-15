# Comic Reading List Schema

Vendored byte for byte from
[json-cbl-standard](https://github.com/ComicReadingLists/json-cbl-standard),
[schema/1.0/comic-reading-list.schema.json](https://github.com/ComicReadingLists/json-cbl-standard/blob/dea268c508b9/schema/1.0/comic-reading-list.schema.json)
at commit `dea268c` (2024-09-03).

_An ordered list of comic book issues which have been composed for the purpose
of reading_

## Properties

- <a id="properties/fileDetails"></a>**`fileDetails`** _(object, required)_
    - <a id="properties/fileDetails/properties/version"></a>**`version`**
      _(number, required)_
    - <a id="properties/fileDetails/properties/UUID"></a>**`UUID`** _(string,
      required)_
- <a id="properties/listDetails"></a>**`listDetails`** _(object, required)_
    - <a id="properties/listDetails/properties/name"></a>**`name`** _(string,
      required)_
    - <a id="properties/listDetails/properties/description"></a>**`description`**
      _(string)_
    - <a id="properties/listDetails/properties/publisher"></a>**`publisher`**
      _(string)_
    - <a id="properties/listDetails/properties/imprint"></a>**`imprint`**
      _(string)_
    - <a id="properties/listDetails/properties/startYear"></a>**`startYear`**
      _(integer)_: Minimum: `1900`. Maximum: `2100`.
    - <a id="properties/listDetails/properties/endYear"></a>**`endYear`**
      _(integer)_: Minimum: `1900`. Maximum: `2100`.
    - <a id="properties/listDetails/properties/type"></a>**`type`** _(string)_:
      Describes the scope of the reading list in impact over the publisher's
      works, ranging from 'master' lists (all publisher works), to 'universal'
      events (which include crossovers universe-wide), to 'story' events (arcs
      contained to a single character). Must be one of: "master",
      "interuniversal", "universal", "team", "character", or "story".
    - <a id="properties/listDetails/properties/tags"></a>**`tags`** _(array)_
        - <a id="properties/listDetails/properties/tags/items"></a>**Items**
          _(string)_: Tags may be used to identify list source, characters,
          teams and eras of the list. Entries should be all lower case with
          proper grammar.
    - <a id="properties/listDetails/properties/coverImageURLs"></a>**`coverImageURLs`**
      _(array)_
        - <a id="properties/listDetails/properties/coverImageURLs/items"></a>**Items**
          _(string, format: uri)_: Must match pattern: `^https?://`
          ([Test](https://regexr.com/?expression=%5Ehttps%3F%3A//)).
    - <a id="properties/listDetails/properties/relationships"></a>**`relationships`**
      _(array)_: Links to other reading lists which occur before or after this
      list.
        - <a id="properties/listDetails/properties/relationships/items"></a>**Items**
          _(object)_
            - <a id="properties/listDetails/properties/relationships/items/properties/name"></a>**`name`**
              _(string, required)_
            - <a id="properties/listDetails/properties/relationships/items/properties/UUID"></a>**`UUID`**
              _(string, required)_
            - <a id="properties/listDetails/properties/relationships/items/properties/relationship"></a>**`relationship`**
              _(string, required)_: Must be one of: "previous" or "following".
    - <a id="properties/listDetails/properties/source"></a>**`source`**
      _(array)_: Websites containing useful information about this reading list.
        - <a id="properties/listDetails/properties/source/items"></a>**Items**
          _(object)_
            - <a id="properties/listDetails/properties/source/items/properties/name"></a>**`name`**
              _(string, required)_: Field should be written in capital case with
              spaces, using the full name of the source.
            - <a id="properties/listDetails/properties/source/items/properties/url"></a>**`url`**
              _(string, format: uri)_: Must match pattern: `^https?://`
              ([Test](https://regexr.com/?expression=%5Ehttps%3F%3A//)).
            - <a id="properties/listDetails/properties/source/items/properties/id"></a>**`id`**
              _(string)_
- <a id="properties/notes"></a>**`notes`** _(string)_
- <a id="properties/issueList"></a>**`issueList`** _(array, required)_
    - <a id="properties/issueList/items"></a>**Items** _(object)_
        - <a id="properties/issueList/items/properties/seriesName"></a>**`seriesName`**
          _(string, required)_
        - <a id="properties/issueList/items/properties/seriesStartYear"></a>**`seriesStartYear`**
          _(integer, required)_: Minimum: `1900`. Maximum: `2100`.
        - <a id="properties/issueList/items/properties/issueNumber"></a>**`issueNumber`**
          _(string, required)_
        - <a id="properties/issueList/items/properties/issueCoverDate"></a>**`issueCoverDate`**
          _(string, format: date, required)_
        - <a id="properties/issueList/items/properties/issueType"></a>**`issueType`**
          _(string)_: Must be one of: "Event Core", "Event Tie-In", "Event One
          Shot", or "Ongoing".
        - <a id="properties/issueList/items/properties/id"></a>**`id`**
          _(array)_
            - <a id="properties/issueList/items/properties/id/items"></a>**Items**
                - <a id="properties/issueList/items/properties/id/items/properties/name"></a>**`name`**
                  _(string, required)_: Must be one of: "comicvine", "metron",
                  or "grandComicsDatabase".
                - <a id="properties/issueList/items/properties/id/items/properties/series"></a>**`series`**
                  _(string, required)_
                - <a id="properties/issueList/items/properties/id/items/properties/issue"></a>**`issue`**
                  _(string, required)_
