"""Pydantic v2 config models, TOML loader, and compiled-in defaults."""

from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from interceptor.constants import CONFIG_FILE


# ---------------------------------------------------------------------------
# Config sub-models
# ---------------------------------------------------------------------------

class GeneralConfig(BaseModel):
    """Top-level general settings."""

    model_config = ConfigDict(extra="ignore")

    backend: str = "claude"
    language: str = "en"
    env: str = "prod"


class RoutingWeights(BaseModel):
    """Scoring formula weights (must sum to 1.0 by convention)."""

    model_config = ConfigDict(extra="ignore")

    trigger: float = 0.60
    context: float = 0.25
    recency: float = 0.15


class RoutingConfig(BaseModel):
    """Routing thresholds and weights."""

    model_config = ConfigDict(extra="ignore")

    min_confidence: float = 0.55
    clarity_gap: float = 0.15
    weights: RoutingWeights = RoutingWeights()


class BackendModelConfig(BaseModel):
    """Per-backend model configuration."""

    model_config = ConfigDict(extra="ignore")

    model: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7


class BackendsConfig(BaseModel):
    """Backend registry — one entry per supported backend."""

    model_config = ConfigDict(extra="ignore")

    claude: BackendModelConfig = BackendModelConfig(
        model="claude-sonnet-4-20250514", max_tokens=8192, temperature=0.3
    )
    openai: BackendModelConfig = BackendModelConfig(
        model="gpt-4o", max_tokens=4096, temperature=0.7
    )


class PluginsConfig(BaseModel):
    """Plugin system settings."""

    model_config = ConfigDict(extra="ignore")

    max_loaded: int = 10
    enabled: bool = True


class Config(BaseModel):
    """Root configuration — all fields have compiled-in defaults."""

    model_config = ConfigDict(extra="ignore")

    general: GeneralConfig = GeneralConfig()
    routing: RoutingConfig = RoutingConfig()
    backends: BackendsConfig = BackendsConfig()
    plugins: PluginsConfig = PluginsConfig()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_default_config() -> Config:
    """Return a Config populated entirely from compiled-in defaults."""
    return Config()


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge *overlay* into *base* (non-destructive)."""
    merged = dict(base)
    for key, value in overlay.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


_ENV_MAP: dict[str, list[str]] = {
    "INTERCEPTOR_BACKEND": ["general", "backend"],
    "INTERCEPTOR_LANGUAGE": ["general", "language"],
    "INTERCEPTOR_ENV": ["general", "env"],
    "INTERCEPTOR_ROUTING_MIN_CONFIDENCE": ["routing", "min_confidence"],
    "INTERCEPTOR_ROUTING_CLARITY_GAP": ["routing", "clarity_gap"],
}


def _apply_env_overrides(data: dict[str, Any]) -> dict[str, Any]:
    """Apply environment variable overrides on top of *data*."""
    for env_var, key_path in _ENV_MAP.items():
        raw = os.environ.get(env_var)
        if raw is None:
            continue
        target = data
        for segment in key_path[:-1]:
            target = target.setdefault(segment, {})
        leaf = key_path[-1]
        # coerce numeric strings for float fields
        if leaf in {"min_confidence", "clarity_gap"}:
            try:
                target[leaf] = float(raw)
            except ValueError:
                pass
        else:
            target[leaf] = raw
    return data


# ---------------------------------------------------------------------------
# Public loader
# ---------------------------------------------------------------------------

def load_config(path: Path | None = None) -> Config:
    """Load config from TOML file + env overlays.  Never raises on bad input.

    Resolution order (highest priority wins):
        1. Environment variables ($INTERCEPTOR_*)
        2. User config file
        3. Compiled-in defaults
    """
    config_path = path or CONFIG_FILE
    defaults = get_default_config().model_dump()
    file_data: dict[str, Any] = {}

    if config_path.exists():
        try:
            file_data = tomllib.loads(config_path.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, OSError) as exc:
            print(
                f"⚠️  Config parse error in {config_path}: {exc}. Using defaults.",
                file=sys.stderr,
            )

    merged = _deep_merge(defaults, file_data)
    merged = _apply_env_overrides(merged)

    try:
        return Config.model_validate(merged)
    except ValidationError as exc:
        print(
            f"⚠️  Config validation error: {exc}. Using defaults.",
            file=sys.stderr,
        )
        return get_default_config()
