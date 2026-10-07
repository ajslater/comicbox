"""
Config: the files and env vars a run would read, and what they say.

A run logs most of these findings once, as a warning, and carries on:
a broken user config is skipped, a typo'd key is silently dropped, a
legacy env var is ignored. The doctor turns each into a row, by calling
the code the warning comes from rather than by capturing log output.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from difflib import get_close_matches
from functools import cache, partial
from importlib.resources import files
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from confuse import ConfigError, ConfigReadError, Configuration, yaml_util
from confuse.core import DEFAULT_FILENAME
from confuse.templates import MappingTemplate
from confuse.templates import Optional as OptionalTemplate

from comicbox.cli.parser import FOLDED_DESTS
from comicbox.config.online.template import _PER_SOURCE_TUNING_TEMPLATE
from comicbox.config.read import _LEGACY_ENV_VARS, _config_path
from comicbox.doctor.result import CheckResult, Status
from comicbox.formats.base.online import SOURCE_NAMES
from comicbox.version import PACKAGE_NAME

if TYPE_CHECKING:
    from collections.abc import Iterator

    from comicbox.doctor.context import Check, DoctorContext

SECTION = "Config"

_ENV_PREFIX = f"{PACKAGE_NAME.upper()}_"
_ENV_SEP = "__"
_CONFIG_DIR_ENV = f"{PACKAGE_NAME.upper()}DIR"
# Set, it looks like it would load a file. Only --config does.
_IGNORED_CONFIG_ENV = f"{_ENV_PREFIX}GENERAL{_ENV_SEP}CONFIG"

# Maps keyed by source name, and the template each source's block follows.
# confuse validates the types in a block but drops keys it doesn't know,
# so the doctor checks both the names and the keys.
_SOURCE_KEYED: Mapping[str, MappingTemplate[Any, Any]] = MappingProxyType(
    {"comicbox.online.tuning.per_source": _PER_SOURCE_TUNING_TEMPLATE}
)

_row = partial(CheckResult, SECTION)


def _new_configuration() -> Configuration:
    return Configuration(PACKAGE_NAME, modname=PACKAGE_NAME, read=False)


def _read_error(exc: Exception) -> str:
    """Say why a config file couldn't be read, without repeating its path."""
    reason = exc.reason if isinstance(exc, ConfigReadError) else exc
    if isinstance(reason, FileNotFoundError):
        return "not found"
    if isinstance(reason, OSError):
        return reason.strerror or str(reason)
    if mark := getattr(reason, "problem_mark", None):
        problem = getattr(reason, "problem", None) or "invalid YAML"
        return f"{problem} at line {mark.line + 1}, column {mark.column + 1}"
    return str(reason or exc)


def _cli_config_path(ctx: DoctorContext) -> Path | None:
    """Return the ``--config`` file a run with these args would load."""
    path = _config_path(ctx.args)
    return Path(path).expanduser() if path else None


def _user_config_path() -> Path:
    """Where confuse looks for the user config. Creates its directory."""
    return Path(_new_configuration().user_config_path())


def _check_cli_config(path: Path) -> CheckResult:
    try:
        _new_configuration().set_file(str(path))
    except ConfigReadError as exc:
        return _row(
            "--config",
            Status.MISCONFIGURED,
            found=path,
            detail=_read_error(exc),
            fix="fix the file or the --config path",
        )
    return _row("--config", Status.OK, found=path, detail="parsed")


def _check_user_config() -> CheckResult:
    config = _new_configuration()
    path = Path(config.user_config_path())
    notes = [f"from ${_CONFIG_DIR_ENV}"] if _CONFIG_DIR_ENV in os.environ else []
    try:
        config.read(user=True, defaults=False)
    except (ConfigError, TypeError, ValueError) as exc:
        return _row(
            "user config",
            Status.MISCONFIGURED,
            found=path,
            detail=" · ".join([f"skipped: {_read_error(exc)}", *notes]),
            fix="fix it, or move it aside to run on defaults",
        )
    notes.insert(0, "parsed" if path.exists() else "none; defaults apply")
    return _row("user config", Status.OK, found=path, detail=" · ".join(notes))


def check_files(ctx: DoctorContext) -> Iterator[CheckResult]:
    """Each config file a run reads: the ``--config`` file, then the user config."""
    if path := _cli_config_path(ctx):
        yield _check_cli_config(path)
    yield _check_user_config()


def check_values(ctx: DoctorContext) -> Iterator[CheckResult]:
    """
    Validate the layered config exactly as a run would.

    A run turns these errors into a one-line exit; the doctor reports them
    and keeps going. On success the later checks get the settings.
    """
    from comicbox.config import get_config

    try:
        ctx.settings = get_config(ctx.args)
    except ConfigReadError:
        # Only the --config file raises this here (a broken user config
        # is skipped), and its own row already says why.
        return
    except (ConfigError, ValueError, TypeError) as exc:
        yield _row(
            "values",
            Status.MISCONFIGURED,
            detail=str(exc),
            fix="fix the setting named above",
        )
        return
    yield _row("values", Status.OK, detail="validated")


def _merge_path(tree: dict[str, Any], dotted: str) -> None:
    """Add a dotted key path to a nested mapping."""
    *parents, leaf = dotted.split(".")
    node = tree
    for part in parents:
        node = node.setdefault(part, {})
    node.setdefault(leaf, None)


@cache
def _known_tree() -> Mapping[str, Any]:
    """
    Every key a config file may set: the shipped defaults, plus the shorthands.

    ``config_default.yaml`` names every setting
    (tests/unit/test_config_defaults_drift.py keeps it complete). The
    folded CLI shorthands have no default but are read all the same.
    """
    text = files(PACKAGE_NAME).joinpath(DEFAULT_FILENAME).read_text()
    tree = yaml_util.load_yaml_string(text, DEFAULT_FILENAME)
    for dotted in FOLDED_DESTS:
        _merge_path(tree[PACKAGE_NAME], dotted)
    return tree


def _template_tree(template: MappingTemplate[Any, Any]) -> dict[str, Any]:
    """Nest the keys a confuse ``MappingTemplate`` reads."""
    tree: dict[str, Any] = {}
    for key, subtemplate in template.subtemplates.items():
        inner = subtemplate
        while isinstance(inner, OptionalTemplate):
            inner = inner.subtemplate
        tree[key] = (
            _template_tree(inner) if isinstance(inner, MappingTemplate) else None
        )
    return tree


def _unknown_source_blocks(
    blocks: Any, template: MappingTemplate[Any, Any], path: str
) -> Iterator[tuple[str, tuple[str, ...]]]:
    """Yield unknown source names in a source-keyed map, then unknown keys in each block."""
    if not isinstance(blocks, Mapping):
        return
    known_block = _template_tree(template)
    for raw_name, block in blocks.items():
        name = str(raw_name)
        if name not in SOURCE_NAMES:
            yield f"{path}.{name}", SOURCE_NAMES
        elif isinstance(block, Mapping):
            yield from _unknown_paths(block, known_block, f"{path}.{name}.")


def _unknown_paths(
    node: Mapping[Any, Any], known: Mapping[str, Any], prefix: str = ""
) -> Iterator[tuple[str, tuple[str, ...]]]:
    """
    Yield each key path in ``node`` that ``known`` lacks, with its valid siblings.

    A map the defaults ship empty (``general.metadata``) holds data, not
    settings, so its keys are anyone's.
    """
    for raw_key, value in node.items():
        key = str(raw_key)
        path = f"{prefix}{key}"
        if key not in known:
            yield path, tuple(known)
            continue
        if template := _SOURCE_KEYED.get(path):
            yield from _unknown_source_blocks(value, template, path)
            continue
        known_child = known[key]
        if (
            isinstance(value, Mapping)
            and isinstance(known_child, Mapping)
            and known_child
        ):
            yield from _unknown_paths(value, known_child, f"{path}.")


def _unknown_key_row(
    found: str | Path, path: str, siblings: tuple[str, ...]
) -> CheckResult:
    shown = path.removeprefix(f"{PACKAGE_NAME}.")
    parent, _, leaf = shown.rpartition(".")
    fix = ""
    if match := get_close_matches(leaf, siblings, n=1):
        fix = f"did you mean {parent + '.' if parent else ''}{match[0]}?"
    return _row(
        "unknown key",
        Status.WARN,
        found=found,
        detail=f"{shown} is ignored",
        fix=fix,
    )


def _load_yaml(path: Path) -> Mapping[Any, Any]:
    """Load a config file, or {} if it's absent or broken (reported above)."""
    if not path.is_file():
        return {}
    try:
        data = yaml_util.load_yaml(str(path))
    except ConfigError:
        return {}
    return data if isinstance(data, Mapping) else {}


def _env_tree(name: str) -> dict[str, Any]:
    """Build the config tree one ``COMICBOX_*`` env var lands on, as EnvSource does."""
    parts = name.removeprefix(_ENV_PREFIX).lower().split(_ENV_SEP)
    tree: dict[str, Any] = {}
    _merge_path(tree, ".".join((PACKAGE_NAME, *parts)))
    return tree


def check_unknown_keys(ctx: DoctorContext) -> Iterator[CheckResult]:
    """Keys a run silently drops, in each config file and the environment."""
    known = _known_tree()
    candidates = (_cli_config_path(ctx), _user_config_path())
    # --config may name the user config itself; report its keys once.
    paths = {path.resolve(): path for path in candidates if path}
    for path in paths.values():
        for key_path, siblings in _unknown_paths(_load_yaml(path), known):
            yield _unknown_key_row(path, key_path, siblings)
    for name in sorted(os.environ):
        if not name.startswith(_ENV_PREFIX) or name in _LEGACY_ENV_VARS:
            continue
        for key_path, siblings in _unknown_paths(_env_tree(name), known):
            yield _unknown_key_row(f"env {name}", key_path, siblings)


def check_env_vars(_ctx: DoctorContext) -> Iterator[CheckResult]:
    """Env vars that look like settings but are no longer, or never were, read."""
    for old, new in _LEGACY_ENV_VARS.items():
        if old in os.environ:
            yield _row(
                "env var",
                Status.WARN,
                found=old,
                detail="no longer read",
                fix=f"rename it {new}",
            )
    if _IGNORED_CONFIG_ENV in os.environ:
        yield _row(
            "env var",
            Status.WARN,
            found=_IGNORED_CONFIG_ENV,
            detail="doesn't load a config file",
            fix="pass --config PATH instead",
        )


CHECKS: tuple[Check, ...] = (
    (SECTION, "files", check_files),
    (SECTION, "values", check_values),
    (SECTION, "unknown key", check_unknown_keys),
    (SECTION, "env var", check_env_vars),
)
