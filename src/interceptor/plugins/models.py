"""Pydantic models for plugin manifests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

VALID_API_VERSIONS = frozenset({"v1"})

VALID_HOOKS_V1 = frozenset({
    "preroute",
    "postroute",
    "precompile",
    "postcompile",
    "presend",
    "postreceive",
    "prevalidate",
    "postvalidate",
})


class PluginManifest(BaseModel):
    """Validated plugin manifest loaded from plugin.toml."""

    model_config = ConfigDict(extra="ignore")

    name: str
    version: str
    description: str
    author: str | None = None
    hooks: list[str]
    api_version: str
    min_compiler_version: str
    max_compiler_version: str
    config: dict[str, Any] | None = None
    permissions: dict[str, Any] | None = None

    @field_validator("api_version")
    @classmethod
    def _check_api_version(cls, v: str) -> str:
        if v not in VALID_API_VERSIONS:
            msg = f"Unsupported api_version: {v!r} (allowed: {sorted(VALID_API_VERSIONS)})"
            raise ValueError(msg)
        return v

    @field_validator("hooks")
    @classmethod
    def _check_hooks(cls, v: list[str]) -> list[str]:
        for hook in v:
            if hook not in VALID_HOOKS_V1:
                msg = f"Invalid hook name: {hook!r} (allowed: {sorted(VALID_HOOKS_V1)})"
                raise ValueError(msg)
        return v

    @field_validator("min_compiler_version", "max_compiler_version")
    @classmethod
    def _check_version_nonempty(cls, v: str) -> str:
        if not v.strip():
            msg = "Compiler version must be a non-empty string"
            raise ValueError(msg)
        return v


class DiscoveredPlugin(BaseModel):
    """A validated plugin with its manifest and source path."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    manifest: PluginManifest
    path: Path
