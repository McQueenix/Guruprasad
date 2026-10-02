"""Optional configuration from ``pyproject.toml`` or ``pymend.ini``."""
from __future__ import annotations

import configparser
import dataclasses
import os
from typing import List, Optional

try:  # Python 3.11+
    import tomllib  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - depends on Python version
    tomllib = None  # type: ignore[assignment]


@dataclasses.dataclass
class Config:
    select: List[str] = dataclasses.field(default_factory=list)
    ignore: List[str] = dataclasses.field(default_factory=list)
    exclude: List[str] = dataclasses.field(default_factory=list)
    source: Optional[str] = None  # which file the settings came from


def _as_list(value, upper: bool = False) -> List[str]:
    if value is None:
        return []
    items = value.split(",") if isinstance(value, str) else list(value)
    out = [str(v).strip() for v in items if str(v).strip()]
    return [v.upper() for v in out] if upper else out


def _from_mapping(data: dict, source: str) -> Config:
    return Config(
        select=_as_list(data.get("select"), upper=True),
        ignore=_as_list(data.get("ignore"), upper=True),
        exclude=_as_list(data.get("exclude")),
        source=source,
    )


def _load_toml(path: str) -> Optional[Config]:
    if tomllib is None:
        return None
    with open(path, "rb") as handle:
        data = tomllib.load(handle)
    section = data.get("tool", {}).get("pymend")
    return _from_mapping(section, path) if isinstance(section, dict) else None


def _load_ini(path: str) -> Optional[Config]:
    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")
    if not parser.has_section("pymend"):
        return None
    return _from_mapping(dict(parser.items("pymend")), path)


def load_config(explicit: Optional[str] = None, start_dir: Optional[str] = None) -> Config:
    """Load settings from ``explicit`` if given, else from the start directory."""
    if explicit:
        loaded = _load_toml(explicit) if explicit.endswith(".toml") else _load_ini(explicit)
        return loaded or Config(source=explicit)
    base = start_dir or os.getcwd()
    toml_path = os.path.join(base, "pyproject.toml")
    if os.path.isfile(toml_path):
        loaded = _load_toml(toml_path)
        if loaded:
            return loaded
    ini_path = os.path.join(base, "pymend.ini")
    if os.path.isfile(ini_path):
        loaded = _load_ini(ini_path)
        if loaded:
            return loaded
    return Config()
