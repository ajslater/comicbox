# Comicbox

## Properties

- <a id="properties/schema"></a>**`schema`**: Must be:
  `"https://github.com/ajslater/comicbox/blob/main/schemas/v3.0/comicbox-v3.0.schema.json"`.
- <a id="properties/appID"></a>**`appID`** _(string)_
- <a id="properties/comicbox"></a>**`comicbox`** _(object, required)_
    - <a id="properties/comicbox/properties/age_rating"></a>**`age_rating`**
      _(string)_
    - <a id="properties/comicbox/properties/alternative_issue"></a>**`alternative_issue`**
      _(object)_
        - <a id="properties/comicbox/properties/alternative_issue/properties/name"></a>**`name`**
          _(string)_
        - <a id="properties/comicbox/properties/alternative_issue/properties/number"></a>**`number`**
          _(number)_
        - <a id="properties/comicbox/properties/alternative_issue/properties/suffix"></a>**`suffix`**
          _(string)_
    - <a id="properties/comicbox/properties/arcs"></a>**`arcs`** _(object)_: Can
      contain additional properties.
        - <a id="properties/comicbox/properties/arcs/additionalProperties"></a>**Additional
          properties** _(object)_
            - <a id="properties/comicbox/properties/arcs/additionalProperties/properties/identifiers"></a>**`identifiers`**
              _(object)_: Refer to
              _[identifiers.schema.json](identifiers.schema.md)_.
            - <a id="properties/comicbox/properties/arcs/additionalProperties/properties/number"></a>**`number`**
              _(integer)_
    - <a id="properties/comicbox/properties/bookmark"></a>**`bookmark`**
      _(integer)_: Minimum: `0`.
    - <a id="properties/comicbox/properties/characters"></a>**`characters`**:
      Refer to _[identified-objects.schema.json](identified-objects.schema.md)_.
    - <a id="properties/comicbox/properties/collection_title"></a>**`collection_title`**
      _(string)_
    - <a id="properties/comicbox/properties/community_rating"></a>**`community_rating`**
      _(object)_
        - <a id="properties/comicbox/properties/community_rating/properties/average_rating"></a>**`average_rating`**
          _(number, format: decimal)_: Minimum: `0`. Maximum: `5`.
        - <a id="properties/comicbox/properties/community_rating/properties/rating_count"></a>**`rating_count`**
          _(integer)_: Minimum: `1`.
    - <a id="properties/comicbox/properties/country"></a>**`country`**
      _(string)_
    - <a id="properties/comicbox/properties/cover_image"></a>**`cover_image`**
      _(string)_
    - <a id="properties/comicbox/properties/credits"></a>**`credits`**
      _(object)_: Can contain additional properties.
        - <a id="properties/comicbox/properties/credits/additionalProperties"></a>**Additional
          properties**: Refer to _[credit.schema.json](credit.schema.md)_.
    - <a id="properties/comicbox/properties/date"></a>**`date`**: Refer to
      _[date.schema.json](date.schema.md)_.
    - <a id="properties/comicbox/properties/ext"></a>**`ext`** _(string)_
    - <a id="properties/comicbox/properties/genres"></a>**`genres`**: Refer to
      _[identified-objects.schema.json](identified-objects.schema.md)_.
    - <a id="properties/comicbox/properties/identifiers"></a>**`identifiers`**:
      Refer to _[identifiers.schema.json](identifiers.schema.md)_.
    - <a id="properties/comicbox/properties/primary_id_source"></a>**`primary_id_source`**
      _(string)_
    - <a id="properties/comicbox/properties/imprint"></a>**`imprint`**: Refer to
      _[named-identified-object.schema.json](named-identified-object.schema.md)_.
    - <a id="properties/comicbox/properties/issue"></a>**`issue`** _(object)_
        - <a id="properties/comicbox/properties/issue/properties/name"></a>**`name`**
          _(string)_
        - <a id="properties/comicbox/properties/issue/properties/number"></a>**`number`**
          _(number)_
        - <a id="properties/comicbox/properties/issue/properties/suffix"></a>**`suffix`**
          _(string)_
    - <a id="properties/comicbox/properties/language"></a>**`language`**
      _(string)_
    - <a id="properties/comicbox/properties/locations"></a>**`locations`**:
      Refer to _[identified-objects.schema.json](identified-objects.schema.md)_.
    - <a id="properties/comicbox/properties/manga"></a>**`manga`** _(string)_:
      Must be one of: "Yes", "No", or "Unknown".
    - <a id="properties/comicbox/properties/manga_volume"></a>**`manga_volume`**
      _(string)_
    - <a id="properties/comicbox/properties/monochrome"></a>**`monochrome`**
      _(boolean)_
    - <a id="properties/comicbox/properties/notes"></a>**`notes`** _(string)_
    - <a id="properties/comicbox/properties/original_format"></a>**`original_format`**
      _(string)_
    - <a id="properties/comicbox/properties/page_count"></a>**`page_count`**
      _(integer)_: Minimum: `0`.
    - <a id="properties/comicbox/properties/pages"></a>**`pages`** _(object)_
        - <a id="properties/comicbox/properties/pages/patternProperties/%5B0-9%5D%2B"></a>**`[0-9]+`**:
          Refer to _[page.schema.json](page.schema.md)_.
    - <a id="properties/comicbox/properties/prices"></a>**`prices`** _(object)_:
      Can contain additional properties.
        - <a id="properties/comicbox/properties/prices/additionalProperties"></a>**Additional
          properties** _(number, format: decimal)_: Minimum: `0`.
    - <a id="properties/comicbox/properties/protagonist"></a>**`protagonist`**
      _(string)_
    - <a id="properties/comicbox/properties/publisher"></a>**`publisher`**:
      Refer to
      _[named-identified-object.schema.json](named-identified-object.schema.md)_.
    - <a id="properties/comicbox/properties/reading_direction"></a>**`reading_direction`**
      _(string)_: Must be one of: "rtl", "ltr", "ttb", or "btt".
    - <a id="properties/comicbox/properties/remainders"></a>**`remainders`**
      _(array)_
        - <a id="properties/comicbox/properties/remainders/items"></a>**Items**
          _(string)_
    - <a id="properties/comicbox/properties/reprints"></a>**`reprints`**
      _(array)_
        - <a id="properties/comicbox/properties/reprints/items"></a>**Items**:
          Refer to _[reprint.schema.json](reprint.schema.md)_.
    - <a id="properties/comicbox/properties/review"></a>**`review`** _(string)_
    - <a id="properties/comicbox/properties/rights"></a>**`rights`** _(string)_
    - <a id="properties/comicbox/properties/scan_info"></a>**`scan_info`**
      _(string)_
    - <a id="properties/comicbox/properties/series"></a>**`series`**: Refer to
      _[series.schema.json](series.schema.md)_.
    - <a id="properties/comicbox/properties/series_groups"></a>**`series_groups`**
      _(array)_
        - <a id="properties/comicbox/properties/series_groups/items"></a>**Items**
          _(string)_
    - <a id="properties/comicbox/properties/stories"></a>**`stories`**: Refer to
      _[identified-objects.schema.json](identified-objects.schema.md)_.
    - <a id="properties/comicbox/properties/summary"></a>**`summary`**
      _(string)_
    - <a id="properties/comicbox/properties/tagger"></a>**`tagger`** _(string)_
    - <a id="properties/comicbox/properties/tags"></a>**`tags`**: Refer to
      _[identified-objects.schema.json](identified-objects.schema.md)_.
    - <a id="properties/comicbox/properties/teams"></a>**`teams`**: Refer to
      _[identified-objects.schema.json](identified-objects.schema.md)_.
    - <a id="properties/comicbox/properties/title"></a>**`title`** _(string)_
    - <a id="properties/comicbox/properties/universes"></a>**`universes`**
      _(object)_: Can contain additional properties.
        - <a id="properties/comicbox/properties/universes/additionalProperties"></a>**Additional
          properties** _(object)_
            - <a id="properties/comicbox/properties/universes/additionalProperties/properties/designation"></a>**`designation`**
              _(string)_
            - <a id="properties/comicbox/properties/universes/additionalProperties/properties/identifiers"></a>**`identifiers`**:
              Refer to _[identifiers.schema.json](identifiers.schema.md)_.
    - <a id="properties/comicbox/properties/updated_at"></a>**`updated_at`**
      _(string, format: date-time)_
    - <a id="properties/comicbox/properties/urls"></a>**`urls`** _(array)_
        - <a id="properties/comicbox/properties/urls/items"></a>**Items**
          _(string, format: uri)_
    - <a id="properties/comicbox/properties/volume"></a>**`volume`**: Refer to
      _[volume.schema.json](volume.schema.md)_.
