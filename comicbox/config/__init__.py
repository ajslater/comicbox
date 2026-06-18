"""Confuse config for comicbox."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from confuse import Configuration
from confuse.templates import (
    Choice,
    Integer,
    MappingTemplate,
    Number,
    OneOf,
    Optional,
    Sequence,
    String,
)
from loguru import logger

from comicbox._pdf import PAGE_FORMAT_VALUES
from comicbox.config.computed import compute_config
from comicbox.config.online import (
    build_online_settings,
    cns_for_overrides,
    runtime_online_inputs,
)
from comicbox.config.paths import (
    expand_glob_paths,
    post_process_set_for_path,
)
from comicbox.config.read import read_config_sources
from comicbox.config.settings import (
    ComicboxSettings,
    ComputeSettings,
    ConvertSettings,
    GeneralSettings,
    PrintSettings,
    ReadSettings,
    WriteSettings,
)
from comicbox.formats.sources import MetadataSources
from comicbox.version import PACKAGE_NAME

if TYPE_CHECKING:
    from argparse import Namespace

# Any non-Mapping container type — set/frozenset/tuple/list all pass.
_NON_MAPPING_TYPES = (set, frozenset, tuple, list)
_NON_MAPPING_CONTAINER = OneOf(_NON_MAPPING_TYPES)


_RATE_LIMIT_TEMPLATE = MappingTemplate(
    {
        "per_minute": Optional(Integer()),
        "per_day": Optional(Integer()),
        "per_second": Optional(Integer()),
        "per_hour": Optional(Integer()),
    }
)


_PER_SOURCE_TUNING_TEMPLATE = MappingTemplate(
    {
        "auto_threshold": Optional(Number()),
        "effort": Optional(String()),
        "min_confidence": Optional(Number()),
        "disambiguation_margin": Optional(Number()),
        "solo_threshold": Optional(Number()),
        "rate_limit": Optional(_RATE_LIMIT_TEMPLATE),
    }
)


_AUTH_SOURCE_TEMPLATE = MappingTemplate(
    {
        "user": Optional(str),
        "pass": Optional(str),
        "key": Optional(str),
        "url": Optional(str),
    }
)


_ONLINE_TEMPLATE = MappingTemplate(
    {
        "lookup": MappingTemplate(
            {
                "match": String(),
                "prompts": String(),
                "rematch": bool,
                "sources": Optional(_NON_MAPPING_CONTAINER),
                "first_wins": bool,
            }
        ),
        "auth": MappingTemplate(
            {
                "metron": _AUTH_SOURCE_TEMPLATE,
                "comicvine": _AUTH_SOURCE_TEMPLATE,
            }
        ),
        "cache": MappingTemplate(
            {
                "mode": String(),
                "dir": Optional(OneOf((str, Path))),
                "ttl": String(),
            }
        ),
        "tuning": MappingTemplate(
            {
                "auto_threshold": Number(),
                "effort": String(),
                "retry_budget": Integer(),
                "per_source": Optional(dict),
            }
        ),
    }
)


_TEMPLATE = MappingTemplate(
    {
        PACKAGE_NAME: MappingTemplate(
            {
                "general": MappingTemplate(
                    {
                        "config": Optional(OneOf((str, Path))),
                        "recurse": bool,
                        "dry_run": bool,
                        "loglevel": OneOf((String(), Integer())),
                        "dest_path": OneOf((str, Path)),
                        "delete_keys": Optional(_NON_MAPPING_CONTAINER),
                        "delete_orig": bool,
                        "metadata": Optional(dict),
                        "metadata_cli": Optional(Sequence(str)),
                        "metadata_format": Optional(str),
                        "jobs": Integer(),
                        "tagger": Optional(str),
                        "theme": Optional(str),
                    }
                ),
                "read": MappingTemplate(
                    {
                        "formats": Optional(_NON_MAPPING_CONTAINER),
                        "except": Optional(_NON_MAPPING_CONTAINER),
                        "merge_order": Optional(_NON_MAPPING_CONTAINER),
                    }
                ),
                "write": MappingTemplate(
                    {
                        "formats": Optional(_NON_MAPPING_CONTAINER),
                        "replace": bool,
                        "stamp": bool,
                        "stamp_notes": bool,
                        "delete_all_tags": bool,
                    }
                ),
                "print": MappingTemplate(
                    {
                        "phases": Optional(OneOf((*_NON_MAPPING_TYPES, str))),
                        "validate": Optional(bool),
                    }
                ),
                "convert": MappingTemplate(
                    {
                        "cbz": Optional(bool),
                        "rename": Optional(bool),
                        "extract_pages_from": Optional(int),
                        "extract_pages_to": Optional(int),
                        "extract_covers": Optional(bool),
                        "import_paths": Optional(Sequence(OneOf((str, Path)))),
                        "export_formats": Optional(_NON_MAPPING_CONTAINER),
                        "pdf_pages": Choice(("", *PAGE_FORMAT_VALUES)),
                    }
                ),
                "compute": MappingTemplate(
                    {
                        "pages": bool,
                        "page_count": bool,
                    }
                ),
                "online": _ONLINE_TEMPLATE,
                "paths": Optional(OneOf((Sequence(OneOf((str, Path))), None))),
                "computed": Optional(
                    MappingTemplate(
                        {
                            "all_write_formats": frozenset,
                            "read_filename_formats": frozenset,
                            "read_file_formats": frozenset,
                            "read_metadata_lower_filenames": frozenset,
                            "is_read_comments": bool,
                            "is_skip_computed_from_tags": bool,
                        }
                    )
                ),
            }
        )
    }
)


def _resolve_merge_order(
    raw: Any,
) -> tuple[MetadataSources, ...] | None:
    """Convert a list of source names → ordered tuple of `MetadataSources`."""
    if not raw:
        return None
    out: list[MetadataSources] = []
    seen: set[MetadataSources] = set()
    for name in raw:
        try:
            member = MetadataSources[str(name).upper()]
        except KeyError:
            logger.warning(f"read.merge_order: unknown source {name!r}, skipping")
            continue
        if member in seen:
            reason = f"read.merge_order: duplicate source {name!r}"
            raise ValueError(reason)
        seen.add(member)
        out.append(member)
    out.extend(member for member in MetadataSources if member not in seen)
    return tuple(out)


def _build_general_settings(general_block: Any) -> GeneralSettings:
    metadata_cli = general_block.metadata_cli
    return GeneralSettings(
        config=general_block.config,
        recurse=bool(general_block.recurse),
        dry_run=bool(general_block.dry_run),
        loglevel=general_block.loglevel,
        dest_path=general_block.dest_path,
        delete_keys=frozenset(general_block.delete_keys or ()),
        delete_orig=bool(general_block.delete_orig),
        metadata=general_block.metadata,
        metadata_cli=tuple(metadata_cli) if metadata_cli else None,
        metadata_format=general_block.metadata_format,
        jobs=max(1, int(general_block.jobs)),
        tagger=general_block.tagger,
        theme=general_block.theme,
    )


def _build_read_settings(read_block: Any) -> ReadSettings:
    except_raw = getattr(read_block, "except", None)
    return ReadSettings(
        formats=frozenset(read_block.formats or ()),
        except_formats=frozenset(except_raw) if except_raw else None,
        merge_order=_resolve_merge_order(read_block.merge_order),
    )


def _build_write_settings(write_block: Any) -> WriteSettings:
    return WriteSettings(
        formats=frozenset(write_block.formats or ()),
        replace=bool(write_block.replace),
        stamp=bool(write_block.stamp),
        stamp_notes=bool(write_block.stamp_notes),
        delete_all_tags=bool(write_block.delete_all_tags),
    )


def _build_convert_settings(convert_block: Any) -> ConvertSettings:
    return ConvertSettings(
        cbz=convert_block.cbz,
        rename=convert_block.rename,
        extract_pages_from=convert_block.extract_pages_from,
        extract_pages_to=convert_block.extract_pages_to,
        extract_covers=convert_block.extract_covers,
        import_paths=expand_glob_paths(convert_block.import_paths),
        export_formats=frozenset(convert_block.export_formats or ()),
        pdf_pages=convert_block.pdf_pages,
    )


def _build_settings(
    ad: Any,
    args: Namespace | Mapping | None = None,
) -> ComicboxSettings:
    """Convert a validated, computed confuse AttrDict into a ComicboxSettings dataclass."""
    inner: Any = ad.comicbox
    computed: Any = inner.computed

    runtime_inputs = runtime_online_inputs(args)
    online = build_online_settings(
        inner.online, runtime_inputs, cns=cns_for_overrides(args)
    )

    print_block = inner.print
    compute_block = inner.compute
    return ComicboxSettings(
        general=_build_general_settings(inner.general),
        read=_build_read_settings(inner.read),
        write=_build_write_settings(inner.write),
        print=PrintSettings(
            phases=frozenset(print_block.phases or ()),
            validate=bool(print_block.validate),
        ),
        convert=_build_convert_settings(inner.convert),
        compute=ComputeSettings(
            pages=bool(compute_block.pages),
            page_count=bool(compute_block.page_count),
        ),
        online=online,
        paths=tuple(inner.paths or ()),
        all_write_formats=frozenset(computed.all_write_formats),
        read_filename_formats=frozenset(computed.read_filename_formats),
        read_file_formats=frozenset(computed.read_file_formats),
        read_metadata_lower_filenames=frozenset(computed.read_metadata_lower_filenames),
        is_read_comments=bool(computed.is_read_comments),
        is_skip_computed_from_tags=bool(computed.is_skip_computed_from_tags),
    )


def get_config(
    args: Namespace | Mapping | ComicboxSettings | None = None,
    *,
    modname: str = PACKAGE_NAME,
    path: str | Path | None = None,
    box: bool = False,
) -> ComicboxSettings:
    """Get the config dict, layering env and args over defaults."""
    if isinstance(args, ComicboxSettings):
        return post_process_set_for_path(args, path, box=box)
    if isinstance(args, Mapping):
        args = dict(args)

    config = Configuration(PACKAGE_NAME, modname=modname, read=False)
    read_config_sources(config, args)

    config_program = config[PACKAGE_NAME]
    compute_config(config_program)

    ad = config.get(_TEMPLATE)
    settings = _build_settings(ad, args=args)
    return post_process_set_for_path(settings, path, box=box)
