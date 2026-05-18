"""
Online metadata source providers (Metron, ComicVine, …).

Each provider exposes the small ABC declared in `base.py`. The
`ComicboxOnlineLookup` mixin instantiates one provider per active
source for the run and walks them in the configured merge order.
"""
