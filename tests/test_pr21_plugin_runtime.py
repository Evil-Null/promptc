"""PR-21 tests — plugin runtime: loading, hooks, chaining, failure isolation."""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest

from interceptor.plugins.context import PluginContext
from interceptor.plugins.models import DiscoveredPlugin, PluginManifest
from interceptor.plugins.runtime import LoadedPlugin, PluginRunner, load_plugin


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_TOML = """\
name = "{name}"
version = "1.0.0"
description = "Test plugin"
hooks = [{hooks}]
api_version = "v1"
min_compiler_version = "0.1.0"
max_compiler_version = "99.0.0"
"""


def _write_manifest(
    plugin_dir: Path,
    name: str = "test-plugin",
    hooks: str = '"precompile"',
) -> Path:
    """Write a minimal plugin.toml and return plugin_dir."""
    plugin_dir.mkdir(parents=True, exist_ok=True)
    toml_path = plugin_dir / "plugin.toml"
    toml_path.write_text(_VALID_TOML.format(name=name, hooks=hooks))
    return plugin_dir


def _write_plugin_py(plugin_dir: Path, code: str) -> Path:
    """Write plugin.py with given code and return the file path."""
    py_path = plugin_dir / "plugin.py"
    py_path.write_text(textwrap.dedent(code))
    return py_path


def _make_discovered(
    plugin_dir: Path,
    name: str = "test-plugin",
    hooks: list[str] | None = None,
    config: dict[str, Any] | None = None,
) -> DiscoveredPlugin:
    """Build a DiscoveredPlugin pointing at plugin_dir."""
    return DiscoveredPlugin(
        manifest=PluginManifest(
            name=name,
            version="1.0.0",
            description="Test",
            hooks=hooks or ["precompile"],
            api_version="v1",
            min_compiler_version="0.1.0",
            max_compiler_version="99.0.0",
            config=config,
        ),
        path=plugin_dir,
    )


# ===================================================================
# A — Valid plugin load
# ===================================================================

class TestA_ValidLoad:
    """A valid plugin.py with matching hooks loads successfully."""

    def test_load_returns_loaded_plugin(self, tmp_path: Path) -> None:
        d = tmp_path / "good"
        _write_manifest(d, "good-plugin", '"precompile"')
        _write_plugin_py(d, """\
            class Plugin:
                def precompile(self, text, ctx):
                    return text
        """)
        disc = _make_discovered(d, "good-plugin", ["precompile"])
        result = load_plugin(disc)
        assert result is not None
        assert result.name == "good-plugin"
        assert not result.disabled
        assert "precompile" in result.hooks

    def test_context_populated(self, tmp_path: Path) -> None:
        d = tmp_path / "ctx"
        _write_manifest(d, "ctx-plugin")
        _write_plugin_py(d, """\
            class Plugin:
                def precompile(self, text, ctx):
                    return text
        """)
        disc = _make_discovered(d, "ctx-plugin", ["precompile"], {"key": "val"})
        result = load_plugin(disc)
        assert result is not None
        assert result.context.plugin_name == "ctx-plugin"
        assert result.context.plugin_config == {"key": "val"}
        assert result.context.api_version == "v1"


# ===================================================================
# B — Missing plugin.py
# ===================================================================

class TestB_MissingPluginPy:
    """No plugin.py in plugin directory → load returns None."""

    def test_missing_plugin_py(self, tmp_path: Path) -> None:
        d = tmp_path / "nopy"
        _write_manifest(d, "nopy")
        disc = _make_discovered(d, "nopy")
        result = load_plugin(disc)
        assert result is None


# ===================================================================
# C — Missing Plugin class
# ===================================================================

class TestC_MissingPluginClass:
    """plugin.py exists but has no Plugin class → load returns None."""

    def test_no_plugin_class(self, tmp_path: Path) -> None:
        d = tmp_path / "noclass"
        _write_manifest(d, "noclass")
        _write_plugin_py(d, """\
            def precompile(text, ctx):
                return text
        """)
        disc = _make_discovered(d, "noclass")
        result = load_plugin(disc)
        assert result is None


# ===================================================================
# D — Instantiation failure
# ===================================================================

class TestD_InstantiationFailure:
    """Plugin class constructor raises → load returns None."""

    def test_constructor_raises(self, tmp_path: Path) -> None:
        d = tmp_path / "boom"
        _write_manifest(d, "boom")
        _write_plugin_py(d, """\
            class Plugin:
                def __init__(self):
                    raise RuntimeError("nope")
                def precompile(self, text, ctx):
                    return text
        """)
        disc = _make_discovered(d, "boom")
        result = load_plugin(disc)
        assert result is None


# ===================================================================
# E — Declared hook missing on instance
# ===================================================================

class TestE_DeclaredHookMissing:
    """Manifest declares a hook but Plugin instance lacks it → load fails."""

    def test_missing_declared_hook(self, tmp_path: Path) -> None:
        d = tmp_path / "missinghook"
        _write_manifest(d, "missinghook", '"precompile", "postcompile"')
        _write_plugin_py(d, """\
            class Plugin:
                def precompile(self, text, ctx):
                    return text
        """)
        disc = _make_discovered(d, "missinghook", ["precompile", "postcompile"])
        result = load_plugin(disc)
        assert result is None


# ===================================================================
# F — Undeclared methods ignored
# ===================================================================

class TestF_UndeclaredMethodsIgnored:
    """Plugin may have extra methods not in hooks — they are ignored."""

    def test_extra_methods_ok(self, tmp_path: Path) -> None:
        d = tmp_path / "extra"
        _write_manifest(d, "extra", '"precompile"')
        _write_plugin_py(d, """\
            class Plugin:
                def precompile(self, text, ctx):
                    return text
                def some_helper(self):
                    pass
        """)
        disc = _make_discovered(d, "extra", ["precompile"])
        result = load_plugin(disc)
        assert result is not None
        assert result.hooks == ["precompile"]


# ===================================================================
# G — Precompile hook execution
# ===================================================================

class TestG_PrecompileExecution:
    """PluginRunner dispatches precompile hook correctly."""

    def test_precompile_transforms(self, tmp_path: Path) -> None:
        d = tmp_path / "pre"
        _write_manifest(d, "pre", '"precompile"')
        _write_plugin_py(d, """\
            class Plugin:
                def precompile(self, text, ctx):
                    return text + " [pre]"
        """)
        disc = _make_discovered(d, "pre", ["precompile"])
        lp = load_plugin(disc)
        assert lp is not None
        runner = PluginRunner([lp])
        result = runner.run_hook("precompile", "hello")
        assert result == "hello [pre]"


# ===================================================================
# H — Postcompile hook execution
# ===================================================================

class TestH_PostcompileExecution:
    """PluginRunner dispatches postcompile hook correctly."""

    def test_postcompile_transforms(self, tmp_path: Path) -> None:
        d = tmp_path / "post"
        _write_manifest(d, "post", '"postcompile"')
        _write_plugin_py(d, """\
            class Plugin:
                def postcompile(self, text, ctx):
                    return text + " [post]"
        """)
        disc = _make_discovered(d, "post", ["postcompile"])
        lp = load_plugin(disc)
        assert lp is not None
        runner = PluginRunner([lp])
        result = runner.run_hook("postcompile", "compiled")
        assert result == "compiled [post]"


# ===================================================================
# I — Multi-plugin ordering
# ===================================================================

class TestI_MultiPluginOrder:
    """Plugins execute in registration order. A's output → B's input."""

    def test_order_preserved(self, tmp_path: Path) -> None:
        plugins = []
        for i, tag in enumerate(["alpha", "beta"]):
            d = tmp_path / tag
            _write_manifest(d, tag, '"precompile"')
            _write_plugin_py(d, f"""\
                class Plugin:
                    def precompile(self, text, ctx):
                        return text + " [{tag}]"
            """)
            disc = _make_discovered(d, tag, ["precompile"])
            lp = load_plugin(disc)
            assert lp is not None
            plugins.append(lp)
        runner = PluginRunner(plugins)
        result = runner.run_hook("precompile", "start")
        assert result == "start [alpha] [beta]"


# ===================================================================
# J — Chaining output through pipeline
# ===================================================================

class TestJ_Chaining:
    """Three plugins chaining: each receives previous plugin's output."""

    def test_three_plugin_chain(self, tmp_path: Path) -> None:
        plugins = []
        for tag in ["a", "b", "c"]:
            d = tmp_path / tag
            _write_manifest(d, tag, '"precompile"')
            _write_plugin_py(d, f"""\
                class Plugin:
                    def precompile(self, text, ctx):
                        return text + ">{tag}"
            """)
            disc = _make_discovered(d, tag, ["precompile"])
            lp = load_plugin(disc)
            assert lp is not None
            plugins.append(lp)
        runner = PluginRunner(plugins)
        result = runner.run_hook("precompile", "x")
        assert result == "x>a>b>c"


# ===================================================================
# K — Crash isolation: exception disables plugin, chain continues
# ===================================================================

class TestK_CrashIsolation:
    """Plugin exception → disabled, unmodified data passed to next plugin."""

    def test_crash_mid_chain(self, tmp_path: Path) -> None:
        plugins = []
        # Plugin A: works
        d_a = tmp_path / "a"
        _write_manifest(d_a, "a", '"precompile"')
        _write_plugin_py(d_a, """\
            class Plugin:
                def precompile(self, text, ctx):
                    return text + " [a]"
        """)
        disc_a = _make_discovered(d_a, "a", ["precompile"])
        plugins.append(load_plugin(disc_a))

        # Plugin B: crashes
        d_b = tmp_path / "b"
        _write_manifest(d_b, "b", '"precompile"')
        _write_plugin_py(d_b, """\
            class Plugin:
                def precompile(self, text, ctx):
                    raise RuntimeError("boom")
        """)
        disc_b = _make_discovered(d_b, "b", ["precompile"])
        plugins.append(load_plugin(disc_b))

        # Plugin C: works
        d_c = tmp_path / "c"
        _write_manifest(d_c, "c", '"precompile"')
        _write_plugin_py(d_c, """\
            class Plugin:
                def precompile(self, text, ctx):
                    return text + " [c]"
        """)
        disc_c = _make_discovered(d_c, "c", ["precompile"])
        plugins.append(load_plugin(disc_c))

        runner = PluginRunner([p for p in plugins if p is not None])
        result = runner.run_hook("precompile", "start")
        # A runs, B crashes (input "start [a]" preserved), C gets "start [a]"
        assert result == "start [a] [c]"
        # B should be disabled
        b_plugin = runner._plugins[1]
        assert b_plugin.disabled


# ===================================================================
# L — None return → disable plugin, continue with original
# ===================================================================

class TestL_NoneReturn:
    """Hook returning None disables plugin; previous value preserved."""

    def test_none_return_isolation(self, tmp_path: Path) -> None:
        plugins = []
        # Plugin A: returns None
        d_a = tmp_path / "a"
        _write_manifest(d_a, "a", '"precompile"')
        _write_plugin_py(d_a, """\
            class Plugin:
                def precompile(self, text, ctx):
                    return None
        """)
        disc_a = _make_discovered(d_a, "a", ["precompile"])
        plugins.append(load_plugin(disc_a))

        # Plugin B: works
        d_b = tmp_path / "b"
        _write_manifest(d_b, "b", '"precompile"')
        _write_plugin_py(d_b, """\
            class Plugin:
                def precompile(self, text, ctx):
                    return text + " [b]"
        """)
        disc_b = _make_discovered(d_b, "b", ["precompile"])
        plugins.append(load_plugin(disc_b))

        runner = PluginRunner([p for p in plugins if p is not None])
        result = runner.run_hook("precompile", "original")
        assert result == "original [b]"
        assert runner._plugins[0].disabled


# ===================================================================
# M — Cross-plugin independence: one crash doesn't affect others
# ===================================================================

class TestM_CrossPluginIndependence:
    """Crash in plugin B does not affect plugin A or C hooks."""

    def test_independent_hooks(self, tmp_path: Path) -> None:
        plugins = []

        d_a = tmp_path / "a"
        _write_manifest(d_a, "a", '"precompile", "postcompile"')
        _write_plugin_py(d_a, """\
            class Plugin:
                def precompile(self, text, ctx):
                    return text + " [a:pre]"
                def postcompile(self, text, ctx):
                    return text + " [a:post]"
        """)
        disc_a = _make_discovered(d_a, "a", ["precompile", "postcompile"])
        plugins.append(load_plugin(disc_a))

        d_b = tmp_path / "b"
        _write_manifest(d_b, "b", '"precompile"')
        _write_plugin_py(d_b, """\
            class Plugin:
                def precompile(self, text, ctx):
                    raise ValueError("broken")
        """)
        disc_b = _make_discovered(d_b, "b", ["precompile"])
        plugins.append(load_plugin(disc_b))

        runner = PluginRunner([p for p in plugins if p is not None])

        pre_result = runner.run_hook("precompile", "in")
        assert pre_result == "in [a:pre]"
        assert runner._plugins[1].disabled

        # Postcompile: B is now disabled, A still works
        post_result = runner.run_hook("postcompile", "compiled")
        assert post_result == "compiled [a:post]"


# ===================================================================
# N — Fresh on new invocation (reset)
# ===================================================================

class TestN_ResetFreshInvocation:
    """reset() re-enables disabled plugins for a new invocation."""

    def test_reset_reenables(self, tmp_path: Path) -> None:
        d = tmp_path / "crashy"
        _write_manifest(d, "crashy", '"precompile"')
        _write_plugin_py(d, """\
            call_count = 0
            class Plugin:
                def precompile(self, text, ctx):
                    global call_count
                    call_count += 1
                    if call_count == 1:
                        raise RuntimeError("first time only")
                    return text + " [ok]"
        """)
        disc = _make_discovered(d, "crashy", ["precompile"])
        lp = load_plugin(disc)
        assert lp is not None
        runner = PluginRunner([lp])

        result1 = runner.run_hook("precompile", "first")
        assert result1 == "first"  # crashed, unchanged
        assert runner._plugins[0].disabled

        runner.reset()
        assert not runner._plugins[0].disabled

        result2 = runner.run_hook("precompile", "second")
        assert result2 == "second [ok]"


# ===================================================================
# O — PluginContext fields
# ===================================================================

class TestO_PluginContext:
    """PluginContext contains expected fields."""

    def test_context_immutable(self) -> None:
        ctx = PluginContext(plugin_name="test")
        assert ctx.plugin_name == "test"
        assert ctx.plugin_config == {}
        assert ctx.api_version == "v1"
        with pytest.raises(AttributeError):
            ctx.plugin_name = "hacked"  # type: ignore[misc]

    def test_context_with_config(self) -> None:
        ctx = PluginContext(plugin_name="p", plugin_config={"x": 1})
        assert ctx.plugin_config == {"x": 1}


# ===================================================================
# P — PluginRunner.from_discovered
# ===================================================================

class TestP_FromDiscovered:
    """from_discovered loads plugins and skips failures."""

    def test_mixed_load(self, tmp_path: Path) -> None:
        # Plugin A: valid
        d_a = tmp_path / "a"
        _write_manifest(d_a, "a", '"precompile"')
        _write_plugin_py(d_a, """\
            class Plugin:
                def precompile(self, text, ctx):
                    return text + " [a]"
        """)
        disc_a = _make_discovered(d_a, "a", ["precompile"])

        # Plugin B: no plugin.py
        d_b = tmp_path / "b"
        _write_manifest(d_b, "b", '"precompile"')
        disc_b = _make_discovered(d_b, "b", ["precompile"])

        runner = PluginRunner.from_discovered([disc_a, disc_b])
        assert len(runner.active_plugins) == 1
        result = runner.run_hook("precompile", "hi")
        assert result == "hi [a]"


# ===================================================================
# Q — Unknown hook name passes through
# ===================================================================

class TestQ_UnknownHook:
    """run_hook with invalid hook name returns first arg unchanged."""

    def test_invalid_hook_passthrough(self) -> None:
        runner = PluginRunner([])
        result = runner.run_hook("nonexistent_hook", "data")
        assert result == "data"

    def test_empty_runner(self) -> None:
        runner = PluginRunner([])
        result = runner.run_hook("precompile", "data")
        assert result == "data"


# ===================================================================
# R — plugin.py with syntax error
# ===================================================================

class TestR_SyntaxError:
    """plugin.py with syntax error → load returns None."""

    def test_syntax_error(self, tmp_path: Path) -> None:
        d = tmp_path / "bad"
        _write_manifest(d, "bad")
        _write_plugin_py(d, """\
            class Plugin:
                def precompile(self, text, ctx)  # missing colon
                    return text
        """)
        disc = _make_discovered(d, "bad")
        result = load_plugin(disc)
        assert result is None


# ===================================================================
# S — Plugin receives PluginContext as last arg
# ===================================================================

class TestS_ContextPassedToHook:
    """Hook receives PluginContext as last positional argument."""

    def test_ctx_in_hook(self, tmp_path: Path) -> None:
        d = tmp_path / "ctxcheck"
        _write_manifest(d, "ctxcheck", '"precompile"')
        _write_plugin_py(d, """\
            class Plugin:
                def precompile(self, text, ctx):
                    return text + f" [{ctx.plugin_name}]"
        """)
        disc = _make_discovered(d, "ctxcheck", ["precompile"])
        lp = load_plugin(disc)
        assert lp is not None
        runner = PluginRunner([lp])
        result = runner.run_hook("precompile", "hello")
        assert result == "hello [ctxcheck]"


# ===================================================================
# T — active_plugins property
# ===================================================================

class TestT_ActivePlugins:
    """active_plugins filters out disabled plugins."""

    def test_active_excludes_disabled(self, tmp_path: Path) -> None:
        d = tmp_path / "p"
        _write_manifest(d, "p", '"precompile"')
        _write_plugin_py(d, """\
            class Plugin:
                def precompile(self, text, ctx):
                    return text
        """)
        disc = _make_discovered(d, "p", ["precompile"])
        lp = load_plugin(disc)
        assert lp is not None
        runner = PluginRunner([lp])
        assert len(runner.active_plugins) == 1
        lp.disabled = True
        assert len(runner.active_plugins) == 0
