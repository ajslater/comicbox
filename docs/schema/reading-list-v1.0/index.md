# Reading List 1.0

## Properties

- <a id="properties/schema"></a>**`schema`**: Must be:
  `"https://github.com/ajslater/comicbox/blob/main/schemas/reading-list/v1.0/reading-list-v1.0.schema.json"`.
- <a id="properties/reading_list"></a>**`reading_list`** _(object)_
    - <a id="properties/reading_list/properties/name"></a>**`name`** _(string)_
    - <a id="properties/reading_list/properties/description"></a>**`description`**
      _(string)_
    - <a id="properties/reading_list/properties/list_type"></a>**`list_type`**
      _(string)_: A free string, lowercased: event, story, characters, teams,
      master, creator, or another.
    - <a id="properties/reading_list/properties/ordered"></a>**`ordered`**
      _(boolean)_: False when the order of the entries is not authoritative.
    - <a id="properties/reading_list/properties/start_year"></a>**`start_year`**
      _(integer)_
    - <a id="properties/reading_list/properties/end_year"></a>**`end_year`**
      _(integer)_
    - <a id="properties/reading_list/properties/private"></a>**`private`**
      _(boolean)_: The source marked the list private to its owner.
    - <a id="properties/reading_list/properties/sources"></a>**`sources`**
      _(array)_: One item per place this list came from, in rank order.
        - <a id="properties/reading_list/properties/sources/items"></a>**Items**:
          Refer to _[source.schema.json](source.schema.md)_.
    - <a id="properties/reading_list/properties/previous"></a>**`previous`**
      _(object)_: The list before this one in a reading order.
        - <a id="properties/reading_list/properties/previous/properties/name"></a>**`name`**
          _(string)_
        - <a id="properties/reading_list/properties/previous/properties/kind"></a>**`kind`**
          _(string)_
        - <a id="properties/reading_list/properties/previous/properties/key"></a>**`key`**
          _(string)_
    - <a id="properties/reading_list/properties/next"></a>**`next`** _(object)_:
      The list after this one in a reading order.
        - <a id="properties/reading_list/properties/next/properties/name"></a>**`name`**
          _(string)_
        - <a id="properties/reading_list/properties/next/properties/kind"></a>**`kind`**
          _(string)_
        - <a id="properties/reading_list/properties/next/properties/key"></a>**`key`**
          _(string)_
    - <a id="properties/reading_list/properties/tags"></a>**`tags`** _(array)_
        - <a id="properties/reading_list/properties/tags/items"></a>**Items**
          _(string)_
    - <a id="properties/reading_list/properties/notes"></a>**`notes`**
      _(string)_
    - <a id="properties/reading_list/properties/entries"></a>**`entries`**
      _(array)_: Array order is reading order. An issue may repeat.
        - <a id="properties/reading_list/properties/entries/items"></a>**Items**:
          Refer to _[entry.schema.json](entry.schema.md)_.
