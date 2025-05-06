"""Title to Stories Transform Mixin."""

from glom import SKIP, Check, Coalesce, Invoke, T, Val
from glom.grouping import Group

from comicbox.schemas.comicbox import STORIES_KEY
from comicbox.transforms.base import skip_not
from comicbox.transforms.spec import MetaSpec

TITLE_STORIES_DELIMITER = ";"


def stories_key_transform_to_cb(title_tag):
    """Create a key transformer for a title tag."""
    return MetaSpec(
        key_map={STORIES_KEY: title_tag},
        spec=(
            Invoke(T.split).constants(TITLE_STORIES_DELIMITER),
            Group({Coalesce((Invoke(T.strip)), skip=skip_not, default=SKIP): Val({})}),
        ),
    )


def stories_key_transform_from_cb(title_tag):
    """Create a key transformer for a title tag."""
    return MetaSpec(
        key_map={title_tag: STORIES_KEY},
        spec=([Check(validate=bool)], Invoke(TITLE_STORIES_DELIMITER.join).specs(T)),
    )
