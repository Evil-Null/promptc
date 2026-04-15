"""PR-28 — plugin timeout enforcement: 5s per hook, cross-platform."""

from __future__ import annotations

from pathlib import Path

import pytest


# Reduce timeout for fast test execution; mechanism is identical.
FAST_TIMEOUT = 0.5


def _write_plugin(
    target: Path,
    name: str,
    hooks: list[str],
    *,
    sleep_hook: str | None = None,
    sleep_seconds: float = 0,
    crash_hook: str | None = None,
    marker: str | None = None,
) -> Path:
    """Create a plugin directory with configurable behavior per hook."""
    pdir = target / name
    pdir.mkdir(parents=True, exist_ok=True)

    hooks_toml = ", ".join(f'"{h}"' for h in hooks)
    (pdir / "plugin.toml").write_text(
        f'name = "{name}"\n'
        f'version = "1.0.0"\n'
        f'description = "test plugin"\n'
        f'hooks = [{hooks_toml}]\n'
        'api_version = "v1"\n'
        'min_compiler_version = "0.1.0"\n'
        'max_compiler_version = "99.0.0"\n'
    )

    methods: list[str] = []
    for h in hooks:
        if h == sleep_hook:
            methods.append(
                f"    def {h}(self, data, ctx):\n"
                f"        import time\n"
                f"        time.sleep({sleep_seconds})\n"
                f"        return data\n"
            )
        elif h == crash_hook:
            methods.append(
                f"    def {h}(self, data, ctx):\n"
                f"        raise RuntimeError('boom')\n"
            )
        elif marker:
            methods.append(
                f"    def {h}(self, data, ctx):\n"
                f"        return data + '{marker}'\n"
            )
        else:
            methods.append(
                f"    def {h}(self, data, ctx):\n"
                f"        return data\n"
            )

    (pdir / "plugin.py").write_text("class Plugin:\n" + "\n".join(methods))
    return pdir


# ---------------------------------------------------------------------------
# A. Fast hook works unchanged
# ---------------------------------------------------------------------------


class TestA_FastHookWorks:
    def test_quick_plugin_not_timed_out(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "interceptor.plugins.runtime.HOOK_TIMEOUT_SECONDS", FAST_TIMEOUT
        )
        _write_plugin(tmp_path, "fast", ["prevalidate"], marker=":tagged")

        from interceptor.plugins.discovery import discover_plugins
        from interceptor.plugins.runtime import PluginRunner

        plugins, _ = discover_plugins(tmp_path)
        runner = PluginRunner.from_discovered(plugins)
        result = runner.run_hook("prevalidate", "hello")
        assert result == "hello:tagged"
        assert len(runner.active_plugins) == 1


# ---------------------------------------------------------------------------
# B. Slow hook treated as failure
# ---------------------------------------------------------------------------


class TestB_SlowHookTimesOut:
    def test_exceeding_timeout_disables_plugin(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "interceptor.plugins.runtime.HOOK_TIMEOUT_SECONDS", FAST_TIMEOUT
        )
        _write_plugin(
            tmp_path,
            "sleeper",
            ["prevalidate"],
            sleep_hook="prevalidate",
            sleep_seconds=FAST_TIMEOUT + 1,
        )

        from interceptor.plugins.discovery import discover_plugins
        from interceptor.plugins.runtime import PluginRunner

        plugins, _ = discover_plugins(tmp_path)
        runner = PluginRunner.from_discovered(plugins)
        result = runner.run_hook("prevalidate", "original")

        assert result == "original"
        assert len(runner.active_plugins) == 0


# ---------------------------------------------------------------------------
# C. Timed-out plugin disabled for remainder
# ---------------------------------------------------------------------------


class TestC_DisabledForRemainder:
    def test_timed_out_on_first_hook_skipped_on_second(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "interceptor.plugins.runtime.HOOK_TIMEOUT_SECONDS", FAST_TIMEOUT
        )
        # Plugin declares two hooks; first one sleeps
        _write_plugin(
            tmp_path,
            "multi-sleeper",
            ["prevalidate", "postvalidate"],
            sleep_hook="prevalidate",
            sleep_seconds=FAST_TIMEOUT + 1,
        )

        from interceptor.plugins.discovery import discover_plugins
        from interceptor.plugins.runtime import PluginRunner

        plugins, _ = discover_plugins(tmp_path)
        runner = PluginRunner.from_discovered(plugins)

        # First hook: prevalidate times out → plugin disabled
        r1 = runner.run_hook("prevalidate", "original")
        assert r1 == "original"
        assert len(runner.active_plugins) == 0

        # Second hook: postvalidate skipped because plugin is disabled
        r2 = runner.run_hook("postvalidate", "data")
        assert r2 == "data"


# ---------------------------------------------------------------------------
# D. Fresh per invocation
# ---------------------------------------------------------------------------


class TestD_FreshPerInvocation:
    def test_reset_reenables_after_timeout(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "interceptor.plugins.runtime.HOOK_TIMEOUT_SECONDS", FAST_TIMEOUT
        )
        _write_plugin(
            tmp_path,
            "sleeper",
            ["prevalidate"],
            sleep_hook="prevalidate",
            sleep_seconds=FAST_TIMEOUT + 1,
        )

        from interceptor.plugins.discovery import discover_plugins
        from interceptor.plugins.runtime import PluginRunner

        plugins, _ = discover_plugins(tmp_path)
        runner = PluginRunner.from_discovered(plugins)

        # First invocation: times out
        runner.run_hook("prevalidate", "x")
        assert len(runner.active_plugins) == 0

        # Reset for next invocation
        runner.reset()
        assert len(runner.active_plugins) == 1


# ---------------------------------------------------------------------------
# E. Healthy sibling survives
# ---------------------------------------------------------------------------


class TestE_SiblingSurvives:
    def test_one_timeout_does_not_disable_sibling(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "interceptor.plugins.runtime.HOOK_TIMEOUT_SECONDS", FAST_TIMEOUT
        )
        # "aaa-sleeper" sorts first, sleeps → disabled
        _write_plugin(
            tmp_path,
            "aaa-sleeper",
            ["prevalidate"],
            sleep_hook="prevalidate",
            sleep_seconds=FAST_TIMEOUT + 1,
        )
        # "zzz-healthy" sorts second, runs fine
        _write_plugin(
            tmp_path, "zzz-healthy", ["prevalidate"], marker=":ok"
        )

        from interceptor.plugins.discovery import discover_plugins
        from interceptor.plugins.runtime import PluginRunner

        plugins, _ = discover_plugins(tmp_path)
        runner = PluginRunner.from_discovered(plugins)
        result = runner.run_hook("prevalidate", "hello")

        assert result == "hello:ok"
        assert len(runner.active_plugins) == 1
        assert runner.active_plugins[0].name == "zzz-healthy"


# ---------------------------------------------------------------------------
# F. Original data preserved on timeout
# ---------------------------------------------------------------------------


class TestF_OriginalDataPreserved:
    def test_on_timeout_data_unchanged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "interceptor.plugins.runtime.HOOK_TIMEOUT_SECONDS", FAST_TIMEOUT
        )
        _write_plugin(
            tmp_path,
            "sleeper",
            ["prevalidate"],
            sleep_hook="prevalidate",
            sleep_seconds=FAST_TIMEOUT + 1,
        )

        from interceptor.plugins.discovery import discover_plugins
        from interceptor.plugins.runtime import PluginRunner

        plugins, _ = discover_plugins(tmp_path)
        runner = PluginRunner.from_discovered(plugins)

        original = "this exact string"
        result = runner.run_hook("prevalidate", original)
        assert result is original


# ---------------------------------------------------------------------------
# G. Real runner path
# ---------------------------------------------------------------------------


class TestG_RealRunner:
    def test_timeout_via_real_plugin_runner(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Timeout enforced through real PluginRunner.run_hook, not a wrapper."""
        monkeypatch.setattr(
            "interceptor.plugins.runtime.HOOK_TIMEOUT_SECONDS", FAST_TIMEOUT
        )
        _write_plugin(
            tmp_path,
            "sleeper",
            ["presend"],
            sleep_hook="presend",
            sleep_seconds=FAST_TIMEOUT + 1,
        )

        from interceptor.plugins.discovery import discover_plugins
        from interceptor.plugins.runtime import PluginRunner

        plugins, _ = discover_plugins(tmp_path)
        runner = PluginRunner.from_discovered(plugins)

        result = runner.run_hook("presend", "payload")
        assert result == "payload"
        assert len(runner.active_plugins) == 0


# ---------------------------------------------------------------------------
# H. Real pipeline path
# ---------------------------------------------------------------------------


class TestH_RealPipeline:
    def test_timeout_in_evaluate_result(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Timeout fires through real _evaluate_result prevalidate path."""
        monkeypatch.setattr(
            "interceptor.plugins.runtime.HOOK_TIMEOUT_SECONDS", FAST_TIMEOUT
        )
        _write_plugin(
            tmp_path,
            "sleeper",
            ["prevalidate"],
            sleep_hook="prevalidate",
            sleep_seconds=FAST_TIMEOUT + 1,
        )

        from interceptor.adapters.models import ExecutionResult
        from interceptor.adapters.service import _evaluate_result
        from interceptor.plugins.discovery import discover_plugins
        from interceptor.plugins.runtime import PluginRunner

        plugins, _ = discover_plugins(tmp_path)
        runner = PluginRunner.from_discovered(plugins)

        result = ExecutionResult(backend="claude", text="dirty   ")
        _evaluate_result(result, "plain prompt", plugin_runner=runner)

        # Timed out → text unchanged
        assert result.text == "dirty   "


# ---------------------------------------------------------------------------
# I. No external machinery
# ---------------------------------------------------------------------------


class TestI_NoExternalMachinery:
    def test_timeout_constant_is_5(self) -> None:
        import interceptor.plugins.runtime as rt

        assert rt.HOOK_TIMEOUT_SECONDS == 5

    def test_mechanism_is_thread_based(self) -> None:
        """Verify cross-platform threading, not signal.alarm."""
        import ast

        with open("src/interceptor/plugins/runtime.py") as f:
            source = f.read()

        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name) and node.value.id == "signal":
                    pytest.fail("signal module used — not cross-platform")

        assert "threading" in source


# ---------------------------------------------------------------------------
# J. Non-timeout failure still works
# ---------------------------------------------------------------------------


class TestJ_NonTimeoutFailure:
    def test_exception_still_disables(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "interceptor.plugins.runtime.HOOK_TIMEOUT_SECONDS", FAST_TIMEOUT
        )
        _write_plugin(
            tmp_path,
            "crasher",
            ["prevalidate"],
            crash_hook="prevalidate",
        )

        from interceptor.plugins.discovery import discover_plugins
        from interceptor.plugins.runtime import PluginRunner

        plugins, _ = discover_plugins(tmp_path)
        runner = PluginRunner.from_discovered(plugins)
        result = runner.run_hook("prevalidate", "original")

        assert result == "original"
        assert len(runner.active_plugins) == 0


# ---------------------------------------------------------------------------
# K. No-plugin baseline
# ---------------------------------------------------------------------------


class TestK_NoPluginBaseline:
    def test_no_plugins_no_overhead(self) -> None:
        from interceptor.plugins.runtime import PluginRunner

        runner = PluginRunner([])
        result = runner.run_hook("prevalidate", "text")
        assert result == "text"

    def test_health_pass_without_plugins(self) -> None:
        from interceptor.health import check_plugin_integrity

        result = check_plugin_integrity(Path("/nonexistent"))
        assert result.status == "pass"


# ---------------------------------------------------------------------------
# L. Regression
# ---------------------------------------------------------------------------


class TestL_Regression:
    def test_sample_plugin_still_works_with_timeout(
        self, tmp_path: Path,
    ) -> None:
        """PR-27 sample plugin continues to work under timeout enforcement."""
        import shutil

        sample = Path(__file__).resolve().parent.parent / "examples" / "sample-plugin"
        shutil.copytree(sample, tmp_path / "sample-whitespace-normalizer")

        from interceptor.plugins.discovery import discover_plugins
        from interceptor.plugins.runtime import PluginRunner

        plugins, _ = discover_plugins(tmp_path)
        runner = PluginRunner.from_discovered(plugins)

        result = runner.run_hook("prevalidate", "hello   ")
        assert result == "hello"
        assert len(runner.active_plugins) == 1
