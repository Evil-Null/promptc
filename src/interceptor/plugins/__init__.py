"""Plugin system foundation — manifest models, discovery, registry, and runtime."""

from interceptor.plugins.context import PluginContext
from interceptor.plugins.discovery import discover_plugins, load_plugin_manifest
from interceptor.plugins.models import DiscoveredPlugin, PluginManifest
from interceptor.plugins.registry import PluginRegistry
from interceptor.plugins.runtime import LoadedPlugin, PluginRunner, load_plugin

__all__ = [
    "DiscoveredPlugin",
    "LoadedPlugin",
    "PluginContext",
    "PluginManifest",
    "PluginRegistry",
    "PluginRunner",
    "discover_plugins",
    "load_plugin",
    "load_plugin_manifest",
]
