"""Plugin system foundation — manifest models, discovery, and registry."""

from interceptor.plugins.discovery import discover_plugins, load_plugin_manifest
from interceptor.plugins.models import DiscoveredPlugin, PluginManifest
from interceptor.plugins.registry import PluginRegistry

__all__ = [
    "DiscoveredPlugin",
    "PluginManifest",
    "PluginRegistry",
    "discover_plugins",
    "load_plugin_manifest",
]
