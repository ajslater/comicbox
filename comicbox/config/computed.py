"""Compute values for config before template load."""

from confuse import Subview
from loguru import logger

from comicbox.config.formats import transform_keys_to_formats
from comicbox.config.paths import clean_paths
from comicbox.formats import MetadataFormats
from comicbox.print import PrintPhases
from comicbox.sources import MetadataSources
from comicbox.version import DEFAULT_TAGGER

_FORMATS_WITH_TAGS_WITHOUT_IDS = frozenset(
    {
        MetadataFormats.COMIC_BOOK_INFO,
        MetadataFormats.COMIC_INFO,
        MetadataFormats.COMICTAGGER,
        MetadataFormats.PDF,
        MetadataFormats.PDF_XML,
    }
)


def _ensure_cli_yaml(config):
    """Wrap all cli yaml in brackets if its bare."""
    mds = config["metadata_cli"].get()
    if not mds:
        return
    wrapped_md_list = []
    for md in mds:
        if not md:
            continue
        wrapped_md = "{" + md + "}" if md[0] != "{" else md
        wrapped_md_list.append(wrapped_md)

    config["metadata_cli"].set(tuple(wrapped_md_list))


def _deduplicate_delete_keys(config: Subview):
    """Transform delete keys to a set."""
    delete_keys: list | set | tuple | frozenset = config["delete_keys"].get(list)  # pyright: ignore[reportAssignmentType]
    delete_keys = frozenset({kp.removeprefix("comicbox.") for kp in delete_keys})
    config["delete_keys"].set(delete_keys)


def _parse_print(config: Subview):
    print_fmts: str | None = config["print"].get()  # pyright: ignore[reportAssignmentType]
    if not print_fmts:
        print_fmts = ""
    print_phases = print_fmts.lower()
    enum_print_phases = set()
    for phase in print_phases:
        try:
            enum = PrintPhases(phase)
            enum_print_phases.add(enum)
        except ValueError as exc:
            logger.warning(exc)
    print_fmts_set = frozenset(enum_print_phases)
    config["print"].set(print_fmts_set)


def _set_tagger(config: Subview):
    tagger = config["tagger"].get()
    if not tagger:
        config["tagger"].set(DEFAULT_TAGGER)


def _set_computed(config: Subview):
    write: frozenset = config["write"].get(frozenset)  # pyright: ignore[reportAssignmentType]
    export: frozenset = config["export"].get(frozenset)  # pyright: ignore[reportAssignmentType]·
    all_write_fmts = frozenset(write | export)
    config["computed"]["all_write_formats"].set(all_write_fmts)
    read: frozenset = config["read"].get(frozenset)  # pyright: ignore[reportAssignmentType]·
    rfnf = frozenset(frozenset(MetadataSources.ARCHIVE_FILENAME.value.formats) & read)
    config["computed"]["read_filename_formats"].set(rfnf)
    rff = frozenset(frozenset(MetadataSources.ARCHIVE_FILE.value.formats) & read)
    config["computed"]["read_file_formats"].set(rff)
    rmlf = frozenset(fmt.value.filename.lower() for fmt in rff)
    config["computed"]["read_metadata_lower_filenames"].set(rmlf)
    irc = bool(
        frozenset(frozenset(MetadataSources.ARCHIVE_COMMENT.value.formats) & read)
    )
    config["computed"]["is_read_comments"].set(irc)
    iscft = not bool(_FORMATS_WITH_TAGS_WITHOUT_IDS & read)
    config["computed"]["is_skip_computed_from_tags"].set(iscft)


def compute_config(config_program: Subview):
    """Compute values for config before template load."""
    clean_paths(config_program)
    _ensure_cli_yaml(config_program)
    _deduplicate_delete_keys(config_program)
    transform_keys_to_formats(config_program)
    _parse_print(config_program)
    _set_tagger(config_program)
    _set_computed(config_program)
