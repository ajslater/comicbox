"""
Cross-package data-model constants.

These live in a top-level module (not under `comicbox.formats.*`) so
that low-level consumers like `comicbox.validate.yaml_validator`
can import them without re-entering the formats package during its
own initialization. The `comicbox-native schema and transform packages
re-export them so existing call sites continue to work.
"""

# Comicbox-native root.
ROOT_TAG = "comicbox"
ROOT_KEYPATH = ROOT_TAG

# Top-level comicbox-native field names.
COVER_DATE_KEY = "cover_date"
DATE_KEY = "date"
PAGES_KEY = "pages"
STORE_DATE_KEY = "store_date"
UPDATED_AT_KEY = "updated_at"

# Derived keypaths used by transforms and validators.
COVER_DATE_KEYPATH = f"{DATE_KEY}.{COVER_DATE_KEY}"
STORE_DATE_KEYPATH = f"{DATE_KEY}.{STORE_DATE_KEY}"
PAGES_KEYPATH = f"{ROOT_KEYPATH}.{PAGES_KEY}"
