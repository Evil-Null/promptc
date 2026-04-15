"""In-memory plugin registry built from discovery results."""

from __future__ import annotations

from pathlib import Path

from interceptor.plugins.discovery import discover_plugins
from interceptor.plugins.models import DiscoveredPlugin


class PluginRegistry:
    """Registry of discovered and validated plugins."""

    def __init__(
        self,
        plugins: list[DiscoveredPlugin] | None = None,
        warnings: list[str] | None = None,
    ) -> None:
        self._plugins: dict[str, DiscoveredPlugin] = {
            p.manifest.name: p for p in (plugins or [])
        }
        self._warnings: list[str] = list(warnings or [])

    @classmethod
    def load_all(cls, plugins_dir: Path) -> PluginRegistry:
        """Discover and load all valid plugins from *plugins_dir*."""
        plugins, warnings = discover_plugins(plugins_dir)
        return cls(plugins=plugins, warnings=warnings)

    def list_all(self) -> list[DiscoveredPlugin]:
        """Return all discovered plugins in name order."""
        return [self._plugins[k] for k in sorted(self._plugins)]

    def get(self, name: str) -> DiscoveredPlugin | None:
        """Look up a plugin by name."""
        return self._plugins.get(name)

    def count(self) -> int:
        """Return the number of discovered plugins."""
        return len(self._plugins)

    @property
    def warnings(self) -> list[str]:
        """Return warnings collected during discovery."""
        return list(self._warnings)
