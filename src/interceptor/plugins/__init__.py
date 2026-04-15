"""Plugin system — manifest models, discovery, registry, runtime, and integration."""

from interceptor.plugins.context import PluginContext
from interceptor.plugins.discovery import discover_plugins, load_plugin_manifest
from interceptor.plugins.integration import (
    build_plugin_runner,
    compile_with_plugins,
    execute_stream_with_plugins,
    execute_with_plugins,
    route_with_plugins,
)
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
    "build_plugin_runner",
    "compile_with_plugins",
    "discover_plugins",
    "execute_stream_with_plugins",
    "execute_with_plugins",
    "load_plugin",
    "load_plugin_manifest",
    "route_with_plugins",
]
