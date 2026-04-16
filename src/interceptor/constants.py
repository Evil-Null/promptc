"""XDG paths, version, and compiled-in default values."""

from __future__ import annotations

import os
from pathlib import Path

VERSION = "1.3.0"

_xdg_config = os.environ.get("XDG_CONFIG_HOME", "")
_xdg_data = os.environ.get("XDG_DATA_HOME", "")
_xdg_cache = os.environ.get("XDG_CACHE_HOME", "")

CONFIG_DIR: Path = (
    Path(_xdg_config) if _xdg_config else Path.home() / ".config"
) / "interceptor"

DATA_DIR: Path = (
    Path(_xdg_data) if _xdg_data else Path.home() / ".local" / "share"
) / "interceptor"

CACHE_DIR: Path = (
    Path(_xdg_cache) if _xdg_cache else Path.home() / ".cache"
) / "interceptor"

CONFIG_FILE: Path = CONFIG_DIR / "config.toml"

LOG_DIR: Path = DATA_DIR / "logs"

TEMPLATES_BUILTIN_DIR: Path = Path(__file__).parent / "templates" / "builtin"
TEMPLATES_CUSTOM_DIR: Path = CONFIG_DIR / "templates" / "custom"

PLUGINS_DIR: Path = CONFIG_DIR / "plugins"
