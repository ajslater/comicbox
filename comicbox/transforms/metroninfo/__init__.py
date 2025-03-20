"""MetronInfo.xml Transformer."""

from comicbox.transforms.metroninfo.nested import MetronInfoTransformNestedTags
from comicbox.transforms.xml_transforms import XmlTransform


class MetronInfoTransform(MetronInfoTransformNestedTags):
    """MetronInfo.xml Transformer."""

    TO_COMICBOX_PRE_TRANSFORM = (
        *XmlTransform.TO_COMICBOX_PRE_TRANSFORM,
        MetronInfoTransformNestedTags.parse_arcs,
        MetronInfoTransformNestedTags.parse_prices,
        MetronInfoTransformNestedTags.parse_resources,
        MetronInfoTransformNestedTags.parse_universes,
    )

    FROM_COMICBOX_PRE_TRANSFORM = (
        *XmlTransform.FROM_COMICBOX_PRE_TRANSFORM,
        MetronInfoTransformNestedTags.unparse_arcs,
        MetronInfoTransformNestedTags.unparse_prices,
        MetronInfoTransformNestedTags.unparse_resources,
        MetronInfoTransformNestedTags.unparse_universes,
    )
