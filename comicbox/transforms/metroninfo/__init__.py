"""MetronInfo.xml Transformer."""

from comicbox.transforms.metroninfo.credits import MetronInfoTransformCredits
from comicbox.transforms.xml_transforms import XmlTransform


class MetronInfoTransform(MetronInfoTransformCredits):
    """MetronInfo.xml Transformer."""

    TO_COMICBOX_PRE_TRANSFORM = (
        *XmlTransform.TO_COMICBOX_PRE_TRANSFORM,
        MetronInfoTransformCredits.parse_arcs,
        MetronInfoTransformCredits.parse_credits,
        MetronInfoTransformCredits.parse_manga_volume,
        MetronInfoTransformCredits.parse_publisher,
        MetronInfoTransformCredits.parse_prices,
        MetronInfoTransformCredits.parse_reprints,
        MetronInfoTransformCredits.parse_resources,
        MetronInfoTransformCredits.parse_series,  # must come after reprints
        MetronInfoTransformCredits.parse_universes,
    )

    FROM_COMICBOX_PRE_TRANSFORM = (
        *XmlTransform.FROM_COMICBOX_PRE_TRANSFORM,
        MetronInfoTransformCredits.unparse_arcs,
        MetronInfoTransformCredits.unparse_credits,
        MetronInfoTransformCredits.unparse_prices,
        MetronInfoTransformCredits.unparse_publisher,
        MetronInfoTransformCredits.unparse_resources,
        MetronInfoTransformCredits.unparse_series,
        MetronInfoTransformCredits.unparse_reprints,  # must come after series
        MetronInfoTransformCredits.unparse_universes,
    )
