"""Minimal plugin context passed to hook functions."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from interceptor.constants import VERSION


@dataclass(frozen=True, slots=True)
class PluginContext:
    """Immutable context provided to every plugin hook invocation."""

    plugin_name: str
    plugin_config: dict[str, Any] = field(default_factory=dict)
    compiler_version: str = VERSION
    api_version: str = "v1"
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger("interceptor.plugins"))
