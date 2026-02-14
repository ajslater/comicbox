# Comicbox

## Properties

- <a id="properties/schema"></a>**`schema`**: Must be:
  `"https://github.com/ajslater/comicbox/blob/main/schemas/v2.0/comicbox-v2.0.schema.json"`.
- <a id="properties/appID"></a>**`appID`** _(string)_
- <a id="properties/comicbox"></a>**`comicbox`** _(object, required)_
    - <a id="properties/comicbox/properties/age_rating"></a>**`age_rating`**
      _(string)_
    - <a id="properties/comicbox/properties/alternate_images"></a>**`alternate_images`**
      _(array)_
        - <a id="properties/comicbox/properties/alternate_images/items"></a>**Items**
          _(string)_
    - <a id="properties/comicbox/properties/arcs"></a>**`arcs`** _(object)_
        - <a id="properties/comicbox/properties/arcs/patternProperties/.%2B"></a>**`.+`**
          _(object)_
            - <a id="properties/comicbox/properties/arcs/patternProperties/.%2B/properties/identifiers"></a>**`identifiers`**:
              Refer to _[identifiers.schema.json](#entifiers.schema.json)_.
            - <a id="properties/comicbox/properties/arcs/patternProperties/.%2B/properties/number"></a>**`number`**
              _(integer)_
    - <a id="properties/comicbox/properties/bookmark"></a>**`bookmark`**
      _(integer)_: Minimum: `0`.
    - <a id="properties/comicbox/properties/characters"></a>**`characters`**:
      Refer to
      _[identified-objects.schema.json](#entified-objects.schema.json)_.
    - <a id="properties/comicbox/properties/credits"></a>**`credits`**: Refer to
      _[credits.schema.json](#edits.schema.json)_.
    - <a id="properties/comicbox/properties/country"></a>**`country`**
      _(string)_
    - <a id="properties/comicbox/properties/credit_primaries"></a>**`credit_primaries`**
      _(object)_
        - <a id="properties/comicbox/properties/credit_primaries/patternProperties/.%2B"></a>**`.+`**
            - <a id="properties/comicbox/properties/credit_primaries/patternProperties/.%2B/properties/role"></a>**`role`**:
              Refer to
              _[identifed-object.schema.json](#entifed-object.schema.json)_.
    - <a id="properties/comicbox/properties/collection_title"></a>**`collection_title`**
      _(string)_
    - <a id="properties/comicbox/properties/cover_image"></a>**`cover_image`**
      _(string)_
    - <a id="properties/comicbox/properties/critical_rating"></a>**`critical_rating`**
      _(number)_
    - <a id="properties/comicbox/properties/date"></a>**`date`**: Refer to
      _[date.schema.json](#te.schema.json)_.
    - <a id="properties/comicbox/properties/ext"></a>**`ext`** _(string)_
    - <a id="properties/comicbox/properties/original_format"></a>**`original_format`**
      _(string)_
    - <a id="properties/comicbox/properties/genres"></a>**`genres`**: Refer to
      _[identified-objects.schema.json](#entified-objects.schema.json)_.
    - <a id="properties/comicbox/properties/identifiers"></a>**`identifiers`**:
      Refer to _[identifiers.schema.json](#entifiers.schema.json)_.
    - <a id="properties/comicbox/properties/identifier_primary_source"></a>**`identifier_primary_source`**
      _(object)_
        - <a id="properties/comicbox/properties/identifier_primary_source/properties/source"></a>**`source`**
          _(string, required)_
        - <a id="properties/comicbox/properties/identifier_primary_source/properties/url"></a>**`url`**
          _(string, format: uri)_
    - <a id="properties/comicbox/properties/imprint"></a>**`imprint`**: Refer to
      _[named-identified-object.schema.json](#med-identified-object.schema.json)_.
    - <a id="properties/comicbox/properties/issue"></a>**`issue`** _(object)_
        - <a id="properties/comicbox/properties/issue/properties/name"></a>**`name`**
          _(string)_
        - <a id="properties/comicbox/properties/issue/properties/number"></a>**`number`**
          _(number)_
        - <a id="properties/comicbox/properties/issue/properties/suffix"></a>**`suffix`**
          _(string)_
    - <a id="properties/comicbox/properties/language"></a>**`language`**
      _(string)_
    - <a id="properties/comicbox/properties/manga"></a>**`manga`** _(string)_:
      Must be one of: "Yes", "YesAndRightToLeft", or "No".
    - <a id="properties/comicbox/properties/monochrome"></a>**`monochrome`**
      _(boolean)_
    - <a id="properties/comicbox/properties/page_count"></a>**`page_count`**
      _(integer)_: Minimum: `0`.
    - <a id="properties/comicbox/properties/pages"></a>**`pages`** _(object)_
        - <a id="properties/comicbox/properties/pages/patternProperties/%5B0-9%5D%2B"></a>**`[0-9]+`**:
          Refer to _[page.schema.json](#ge.schema.json)_.
    - <a id="properties/comicbox/properties/publisher"></a>**`publisher`**:
      Refer to
      _[named-identified-object.schema.json](#med-identified-object.schema.json)_.
    - <a id="properties/comicbox/properties/prices"></a>**`prices`** _(object)_
        - <a id="properties/comicbox/properties/prices/patternProperties/%5BA-Za-z%5D%2A"></a>**`[A-Za-z]*`**
          _(number)_: Minimum: `0`.
    - <a id="properties/comicbox/properties/protagonist"></a>**`protagonist`**
      _(string)_
    - <a id="properties/comicbox/properties/reading_direction"></a>**`reading_direction`**
      _(string)_: Must be one of: "rtl", "ltr", "ttb", or "btt".
    - <a id="properties/comicbox/properties/remainder"></a>**`remainder`**
      _(string)_
    - <a id="properties/comicbox/properties/reprints"></a>**`reprints`**
      _(array)_
        - <a id="properties/comicbox/properties/reprints/items"></a>**Items**:
          Refer to _[reprint.schema.json](#print.schema.json)_.
    - <a id="properties/comicbox/properties/review"></a>**`review`** _(string)_
    - <a id="properties/comicbox/properties/rights"></a>**`rights`** _(string)_
    - <a id="properties/comicbox/properties/scan_info"></a>**`scan_info`**
      _(string)_
    - <a id="properties/comicbox/properties/series"></a>**`series`**: Refer to
      _[series.schema.json](#ries.schema.json)_.
    - <a id="properties/comicbox/properties/series_groups"></a>**`series_groups`**
      _(array)_
        - <a id="properties/comicbox/properties/series_groups/items"></a>**Items**
          _(string)_
    - <a id="properties/comicbox/properties/stories"></a>**`stories`**
      _(object)_
    - <a id="properties/comicbox/properties/summary"></a>**`summary`**
      _(string)_
    - <a id="properties/comicbox/properties/tagger"></a>**`tagger`** _(string)_
    - <a id="properties/comicbox/properties/tags"></a>**`tags`**: Refer to
      _[identified-objects.schema.json](#entified-objects.schema.json)_.
    - <a id="properties/comicbox/properties/teams"></a>**`teams`**: Refer to
      _[identified-objects.schema.json](#entified-objects.schema.json)_.
    - <a id="properties/comicbox/properties/title"></a>**`title`** _(string)_
    - <a id="properties/comicbox/properties/universes"></a>**`universes`**
      _(object)_
    - <a id="properties/comicbox/properties/updated_at"></a>**`updated_at`**
      _(string, format: date-time)_
    - <a id="properties/comicbox/properties/volume"></a>**`volume`**: Refer to
      _[volume.schema.json](#lume.schema.json)_.
