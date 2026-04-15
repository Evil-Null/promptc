"""PR-27 — sample plugin: discovery, load, fire, health, removal, crash isolation."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "examples" / "sample-plugin"


def _install_sample(target: Path) -> Path:
    """Copy the sample plugin into *target* plugins directory."""
    dest = target / "sample-whitespace-normalizer"
    shutil.copytree(SAMPLE_DIR, dest)
    return dest


# ---------------------------------------------------------------------------
# A. Discovery
# ---------------------------------------------------------------------------


class TestA_Discovery:
    def test_discovered_via_real_discovery(self, tmp_path: Path) -> None:
        _install_sample(tmp_path)
        from interceptor.plugins.discovery import discover_plugins

        plugins, warnings = discover_plugins(tmp_path)
        assert len(plugins) == 1
        assert plugins[0].manifest.name == "sample-whitespace-normalizer"
        assert not warnings

    def test_manifest_fields_valid(self, tmp_path: Path) -> None:
        _install_sample(tmp_path)
        from interceptor.plugins.discovery import discover_plugins

        plugins, _ = discover_plugins(tmp_path)
        m = plugins[0].manifest
        assert m.version == "1.0.0"
        assert m.api_version == "v1"
        assert m.hooks == ["prevalidate"]
        assert m.author == "interceptor team"


# ---------------------------------------------------------------------------
# B. Loading
# ---------------------------------------------------------------------------


class TestB_Loading:
    def test_loads_via_real_loader(self, tmp_path: Path) -> None:
        _install_sample(tmp_path)
        from interceptor.plugins.discovery import discover_plugins
        from interceptor.plugins.runtime import load_plugin

        plugins, _ = discover_plugins(tmp_path)
        loaded = load_plugin(plugins[0])
        assert loaded is not None
        assert loaded.name == "sample-whitespace-normalizer"
        assert not loaded.disabled

    def test_runner_from_discovered(self, tmp_path: Path) -> None:
        _install_sample(tmp_path)
        from interceptor.plugins.discovery import discover_plugins
        from interceptor.plugins.runtime import PluginRunner

        plugins, _ = discover_plugins(tmp_path)
        runner = PluginRunner.from_discovered(plugins)
        assert len(runner.active_plugins) == 1


# ---------------------------------------------------------------------------
# C. Hook callability
# ---------------------------------------------------------------------------


class TestC_HookMatch:
    def test_declared_hooks_callable(self, tmp_path: Path) -> None:
        _install_sample(tmp_path)
        from interceptor.plugins.discovery import discover_plugins
        from interceptor.plugins.runtime import load_plugin

        plugins, _ = discover_plugins(tmp_path)
        loaded = load_plugin(plugins[0])
        assert loaded is not None
        assert "prevalidate" in loaded.hooks
        assert callable(getattr(loaded.instance, "prevalidate"))

    def test_no_undeclared_hooks(self, tmp_path: Path) -> None:
        _install_sample(tmp_path)
        from interceptor.plugins.discovery import discover_plugins
        from interceptor.plugins.runtime import load_plugin

        plugins, _ = discover_plugins(tmp_path)
        loaded = load_plugin(plugins[0])
        assert loaded is not None
        assert loaded.hooks == ["prevalidate"]


# ---------------------------------------------------------------------------
# D. Health check (direct)
# ---------------------------------------------------------------------------


class TestD_HealthDirect:
    def test_healthy_in_check_plugin_integrity(self, tmp_path: Path) -> None:
        _install_sample(tmp_path)
        from interceptor.health import check_plugin_integrity

        result = check_plugin_integrity(tmp_path)
        assert result.status == "pass"
        assert "sample-whitespace-normalizer" in result.message

    def test_hooks_reported_in_details(self, tmp_path: Path) -> None:
        _install_sample(tmp_path)
        from interceptor.health import check_plugin_integrity

        result = check_plugin_integrity(tmp_path)
        assert "prevalidate" in result.details.get("hooks", "")


# ---------------------------------------------------------------------------
# E. CLI health
# ---------------------------------------------------------------------------


class TestE_CliHealth:
    def test_mycli_health_shows_plugin_healthy(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_sample(tmp_path)
        monkeypatch.setattr("interceptor.constants.PLUGINS_DIR", tmp_path)
        from interceptor.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["health", "--check", "plugin_integrity"])
        assert result.exit_code == 0
        assert "pass" in result.stdout.lower()

    def test_strict_mode_passes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_sample(tmp_path)
        monkeypatch.setattr("interceptor.constants.PLUGINS_DIR", tmp_path)
        from interceptor.cli import app

        runner = CliRunner()
        result = runner.invoke(
            app, ["health", "--check", "plugin_integrity", "--strict"]
        )
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# F. Real pipeline hook firing
# ---------------------------------------------------------------------------


class TestF_PipelineFiring:
    def test_prevalidate_fires_in_evaluate_result(self, tmp_path: Path) -> None:
        """Prove the hook fires through the real _evaluate_result path."""
        _install_sample(tmp_path)
        from interceptor.adapters.models import ExecutionResult
        from interceptor.adapters.service import _evaluate_result
        from interceptor.plugins.discovery import discover_plugins
        from interceptor.plugins.runtime import PluginRunner

        plugins, _ = discover_plugins(tmp_path)
        runner = PluginRunner.from_discovered(plugins)

        dirty = "hello   \nworld  \n  trailing   "
        result = ExecutionResult(backend="claude", text=dirty)
        _evaluate_result(result, "plain prompt", plugin_runner=runner)

        assert result.text == "hello\nworld\n  trailing"

    def test_prevalidate_via_runner_directly(self, tmp_path: Path) -> None:
        _install_sample(tmp_path)
        from interceptor.plugins.discovery import discover_plugins
        from interceptor.plugins.runtime import PluginRunner

        plugins, _ = discover_plugins(tmp_path)
        runner = PluginRunner.from_discovered(plugins)

        assert runner.run_hook("prevalidate", "foo   \nbar  ") == "foo\nbar"


# ---------------------------------------------------------------------------
# G. Determinism
# ---------------------------------------------------------------------------


class TestG_Determinism:
    def test_same_input_same_output_100x(self, tmp_path: Path) -> None:
        _install_sample(tmp_path)
        from interceptor.plugins.discovery import discover_plugins
        from interceptor.plugins.runtime import PluginRunner

        plugins, _ = discover_plugins(tmp_path)
        runner = PluginRunner.from_discovered(plugins)

        dirty = "a  \nb \nc   "
        expected = "a\nb\nc"
        for _ in range(100):
            assert runner.run_hook("prevalidate", dirty) == expected

    def test_empty_string_passthrough(self, tmp_path: Path) -> None:
        _install_sample(tmp_path)
        from interceptor.plugins.discovery import discover_plugins
        from interceptor.plugins.runtime import PluginRunner

        plugins, _ = discover_plugins(tmp_path)
        runner = PluginRunner.from_discovered(plugins)
        assert runner.run_hook("prevalidate", "") == ""

    def test_no_trailing_whitespace_unchanged(self, tmp_path: Path) -> None:
        _install_sample(tmp_path)
        from interceptor.plugins.discovery import discover_plugins
        from interceptor.plugins.runtime import PluginRunner

        plugins, _ = discover_plugins(tmp_path)
        runner = PluginRunner.from_discovered(plugins)
        clean = "already\nclean\ntext"
        assert runner.run_hook("prevalidate", clean) == clean


# ---------------------------------------------------------------------------
# H. Removal returns to baseline
# ---------------------------------------------------------------------------


class TestH_Removal:
    def test_removal_returns_baseline(self, tmp_path: Path) -> None:
        dest = _install_sample(tmp_path)
        from interceptor.health import check_plugin_integrity
        from interceptor.plugins.discovery import discover_plugins

        plugins, _ = discover_plugins(tmp_path)
        assert len(plugins) == 1

        shutil.rmtree(dest)

        plugins2, _ = discover_plugins(tmp_path)
        assert len(plugins2) == 0

        health = check_plugin_integrity(tmp_path)
        assert health.status == "pass"

    def test_empty_runner_passthrough(self) -> None:
        from interceptor.plugins.runtime import PluginRunner

        runner = PluginRunner([])
        dirty = "hello   "
        assert runner.run_hook("prevalidate", dirty) == dirty


# ---------------------------------------------------------------------------
# I. Crash isolation
# ---------------------------------------------------------------------------


class TestI_CrashIsolation:
    def test_crashing_variant_degrades_gracefully(self, tmp_path: Path) -> None:
        """Crashing sibling is disabled; sample plugin still fires."""
        _install_sample(tmp_path)

        crash_dir = tmp_path / "crashing-plugin"
        crash_dir.mkdir()
        (crash_dir / "plugin.toml").write_text(
            'name = "crashing-plugin"\n'
            'version = "1.0.0"\n'
            'description = "crashes"\n'
            'hooks = ["prevalidate"]\n'
            'api_version = "v1"\n'
            'min_compiler_version = "0.1.0"\n'
            'max_compiler_version = "99.0.0"\n'
        )
        (crash_dir / "plugin.py").write_text(
            "class Plugin:\n"
            "    def prevalidate(self, text, ctx):\n"
            "        raise RuntimeError('boom')\n"
        )

        from interceptor.plugins.discovery import discover_plugins
        from interceptor.plugins.runtime import PluginRunner

        plugins, _ = discover_plugins(tmp_path)
        assert len(plugins) == 2

        runner = PluginRunner.from_discovered(plugins)
        # crashing-plugin sorts first, crashes → disabled
        # sample plugin fires second, strips trailing whitespace
        result = runner.run_hook("prevalidate", "hello   ")
        assert result == "hello"

    def test_only_crashing_plugin_still_returns_original(self, tmp_path: Path) -> None:
        """When the only plugin crashes, original value is preserved."""
        crash_dir = tmp_path / "only-crasher"
        crash_dir.mkdir()
        (crash_dir / "plugin.toml").write_text(
            'name = "only-crasher"\n'
            'version = "1.0.0"\n'
            'description = "crashes"\n'
            'hooks = ["prevalidate"]\n'
            'api_version = "v1"\n'
            'min_compiler_version = "0.1.0"\n'
            'max_compiler_version = "99.0.0"\n'
        )
        (crash_dir / "plugin.py").write_text(
            "class Plugin:\n"
            "    def prevalidate(self, text, ctx):\n"
            "        raise RuntimeError('boom')\n"
        )

        from interceptor.plugins.discovery import discover_plugins
        from interceptor.plugins.runtime import PluginRunner

        plugins, _ = discover_plugins(tmp_path)
        runner = PluginRunner.from_discovered(plugins)

        dirty = "hello   "
        assert runner.run_hook("prevalidate", dirty) == dirty


# ---------------------------------------------------------------------------
# J. No-plugin users
# ---------------------------------------------------------------------------


class TestJ_NoPluginBaseline:
    def test_no_plugins_dir_health_pass(self) -> None:
        from interceptor.health import check_plugin_integrity

        result = check_plugin_integrity(Path("/nonexistent"))
        assert result.status == "pass"

    def test_empty_runner_passthrough(self) -> None:
        from interceptor.plugins.runtime import PluginRunner

        runner = PluginRunner([])
        assert runner.run_hook("prevalidate", "text") == "text"


# ---------------------------------------------------------------------------
# K. No side effects
# ---------------------------------------------------------------------------


class TestK_NoSideEffects:
    def test_no_file_writes(self, tmp_path: Path) -> None:
        _install_sample(tmp_path)
        from interceptor.plugins.discovery import discover_plugins
        from interceptor.plugins.runtime import PluginRunner

        plugins, _ = discover_plugins(tmp_path)
        runner = PluginRunner.from_discovered(plugins)

        files_before = set(tmp_path.rglob("*"))
        runner.run_hook("prevalidate", "test   ")
        files_after = set(tmp_path.rglob("*"))
        assert files_before == files_after

    def test_no_env_mutation(self, tmp_path: Path) -> None:
        import os

        _install_sample(tmp_path)
        from interceptor.plugins.discovery import discover_plugins
        from interceptor.plugins.runtime import PluginRunner

        env_before = dict(os.environ)
        plugins, _ = discover_plugins(tmp_path)
        runner = PluginRunner.from_discovered(plugins)
        runner.run_hook("prevalidate", "test   ")
        env_after = dict(os.environ)
        assert env_before == env_after


# ---------------------------------------------------------------------------
# L. Regression
# ---------------------------------------------------------------------------


class TestL_Regression:
    def test_sample_plugin_files_exist(self) -> None:
        """Verify the sample plugin fixture is present in the repo."""
        assert (SAMPLE_DIR / "plugin.toml").is_file()
        assert (SAMPLE_DIR / "plugin.py").is_file()
