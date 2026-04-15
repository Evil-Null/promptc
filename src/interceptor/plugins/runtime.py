"""Plugin runtime — loading, validation, and hook dispatch."""

from __future__ import annotations

import importlib.util
import sys
import threading
import types
from pathlib import Path
from typing import Any

from interceptor.plugins.context import PluginContext
from interceptor.plugins.models import DiscoveredPlugin, VALID_HOOKS_V1

HOOK_TIMEOUT_SECONDS: int = 5


class _HookTimeoutError(Exception):
    """Internal: raised when a plugin hook exceeds the time limit."""


def _call_with_timeout(fn: Any, *args: Any) -> Any:
    """Execute *fn* in a daemon thread with HOOK_TIMEOUT_SECONDS hard limit."""
    result_box: list[Any] = [None]
    error_box: list[BaseException | None] = [None]

    def _target() -> None:
        try:
            result_box[0] = fn(*args)
        except BaseException as exc:
            error_box[0] = exc

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join(timeout=HOOK_TIMEOUT_SECONDS)

    if thread.is_alive():
        raise _HookTimeoutError

    if error_box[0] is not None:
        raise error_box[0]

    return result_box[0]


class LoadedPlugin:
    """A validated, instantiated plugin ready for hook dispatch."""

    __slots__ = ("name", "instance", "hooks", "context", "disabled")

    def __init__(
        self,
        name: str,
        instance: object,
        hooks: list[str],
        context: PluginContext,
    ) -> None:
        self.name = name
        self.instance = instance
        self.hooks = hooks
        self.context = context
        self.disabled = False


def load_plugin(discovered: DiscoveredPlugin) -> LoadedPlugin | None:
    """Load plugin.py from a discovered plugin directory.

    Returns LoadedPlugin on success, None on any failure.  Never raises.
    """
    plugin_py = discovered.path / "plugin.py"
    manifest = discovered.manifest

    if not plugin_py.is_file():
        print(
            f"⚠️  Plugin {manifest.name}: missing plugin.py in {discovered.path}",
            file=sys.stderr,
        )
        return None

    module = _load_module(manifest.name, plugin_py)
    if module is None:
        return None

    plugin_cls = getattr(module, "Plugin", None)
    if plugin_cls is None or not callable(plugin_cls):
        print(
            f"⚠️  Plugin {manifest.name}: no Plugin class in plugin.py",
            file=sys.stderr,
        )
        return None

    try:
        instance = plugin_cls()
    except Exception as exc:
        print(
            f"⚠️  Plugin {manifest.name}: instantiation failed: {exc}",
            file=sys.stderr,
        )
        return None

    for hook_name in manifest.hooks:
        attr = getattr(instance, hook_name, None)
        if attr is None or not callable(attr):
            print(
                f"⚠️  Plugin {manifest.name}: declared hook {hook_name!r} "
                f"missing or not callable",
                file=sys.stderr,
            )
            return None

    ctx = PluginContext(
        plugin_name=manifest.name,
        plugin_config=manifest.config or {},
        api_version=manifest.api_version,
    )

    return LoadedPlugin(
        name=manifest.name,
        instance=instance,
        hooks=list(manifest.hooks),
        context=ctx,
    )


def _load_module(name: str, path: Path) -> types.ModuleType | None:
    """Import a Python file as a module. Returns None on failure."""
    module_name = f"_interceptor_plugin_{name}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            print(
                f"⚠️  Plugin {name}: could not create module spec from {path}",
                file=sys.stderr,
            )
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception as exc:
        print(
            f"⚠️  Plugin {name}: failed to load plugin.py: {exc}",
            file=sys.stderr,
        )
        return None


class PluginRunner:
    """Manages loaded plugins and dispatches hooks with failure isolation."""

    def __init__(self, plugins: list[LoadedPlugin] | None = None) -> None:
        self._plugins: list[LoadedPlugin] = list(plugins or [])

    @classmethod
    def from_discovered(cls, discovered: list[DiscoveredPlugin]) -> PluginRunner:
        """Load all discovered plugins, skipping those that fail to load."""
        loaded: list[LoadedPlugin] = []
        for d in discovered:
            lp = load_plugin(d)
            if lp is not None:
                loaded.append(lp)
        return cls(loaded)

    @property
    def active_plugins(self) -> list[LoadedPlugin]:
        """Return plugins that are not disabled."""
        return [p for p in self._plugins if not p.disabled]

    def run_hook(self, hook_name: str, *args: Any) -> Any:
        """Dispatch a hook across all active plugins that declare it.

        Plugins execute in registration order.
        Each plugin receives the output of the previous one as the first arg.
        On failure: plugin is disabled, original input to that hook step is preserved.
        Returns the final transformed value (first positional arg).
        """
        if hook_name not in VALID_HOOKS_V1:
            return args[0] if args else None

        current_value = args[0] if args else None
        rest_args = args[1:] if len(args) > 1 else ()

        for plugin in self._plugins:
            if plugin.disabled:
                continue
            if hook_name not in plugin.hooks:
                continue

            hook_fn = getattr(plugin.instance, hook_name, None)
            if hook_fn is None or not callable(hook_fn):
                continue

            try:
                result = _call_with_timeout(
                    hook_fn, current_value, *rest_args, plugin.context,
                )
            except _HookTimeoutError:
                print(
                    f"⚠️  Plugin {plugin.name}: hook {hook_name} timed out "
                    f"after {HOOK_TIMEOUT_SECONDS}s",
                    file=sys.stderr,
                )
                plugin.disabled = True
                continue
            except Exception as exc:
                print(
                    f"⚠️  Plugin {plugin.name}: hook {hook_name} raised "
                    f"{type(exc).__name__}: {exc}",
                    file=sys.stderr,
                )
                plugin.disabled = True
                continue

            if result is None:
                print(
                    f"⚠️  Plugin {plugin.name}: hook {hook_name} returned None, "
                    f"disabling plugin",
                    file=sys.stderr,
                )
                plugin.disabled = True
                continue

            current_value = result

        return current_value

    def reset(self) -> None:
        """Re-enable all plugins for a fresh invocation."""
        for p in self._plugins:
            p.disabled = False
