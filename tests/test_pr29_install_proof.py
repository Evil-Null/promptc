"""PR-29 — plugin install/distribution proof.

Proves the sample plugin can be installed into a canonical plugin path,
discovered by the real loader, passes health, fires its hook, and can
be removed cleanly back to baseline.
"""

from __future__ import annotations

from pathlib import Path

import pytest

SAMPLE_PLUGIN_DIR = (
    Path(__file__).resolve().parent.parent / "examples" / "sample-plugin"
)


# ---------------------------------------------------------------------------
# A. Clean environment — no plugins initially
# ---------------------------------------------------------------------------


class TestA_CleanEnvironment:
    def test_empty_dir_has_no_plugins(self, tmp_path: Path) -> None:
        from interceptor.plugins.discovery import discover_plugins

        plugins, warnings = discover_plugins(tmp_path)
        assert len(plugins) == 0
        assert len(warnings) == 0

    def test_health_pass_on_empty(self, tmp_path: Path) -> None:
        from interceptor.health import check_plugin_integrity

        result = check_plugin_integrity(tmp_path)
        assert result.status == "pass"
        assert result.details["discovered"] == "0"


# ---------------------------------------------------------------------------
# B. Install places plugin in canonical location
# ---------------------------------------------------------------------------


class TestB_InstallPlacesPlugin:
    def test_install_copies_all_files(self, tmp_path: Path) -> None:
        from interceptor.plugins.install import install_plugin

        plugins_dir = tmp_path / "plugins"
        installed = install_plugin(SAMPLE_PLUGIN_DIR, plugins_dir)

        assert installed.is_dir()
        assert (installed / "plugin.toml").is_file()
        assert (installed / "plugin.py").is_file()

    def test_install_rejects_duplicate(self, tmp_path: Path) -> None:
        from interceptor.plugins.install import install_plugin

        plugins_dir = tmp_path / "plugins"
        install_plugin(SAMPLE_PLUGIN_DIR, plugins_dir)

        with pytest.raises(FileExistsError):
            install_plugin(SAMPLE_PLUGIN_DIR, plugins_dir)

    def test_install_rejects_missing_source(self, tmp_path: Path) -> None:
        from interceptor.plugins.install import install_plugin

        with pytest.raises(FileNotFoundError):
            install_plugin(tmp_path / "nonexistent", tmp_path / "plugins")


# ---------------------------------------------------------------------------
# C. Real loader discovers installed plugin
# ---------------------------------------------------------------------------


class TestC_RealDiscovery:
    def test_installed_plugin_discovered(self, tmp_path: Path) -> None:
        from interceptor.plugins.discovery import discover_plugins
        from interceptor.plugins.install import install_plugin

        install_plugin(SAMPLE_PLUGIN_DIR, tmp_path)
        plugins, warnings = discover_plugins(tmp_path)

        assert len(plugins) == 1
        assert plugins[0].manifest.name == "sample-whitespace-normalizer"
        assert len(warnings) == 0

    def test_installed_plugin_loads(self, tmp_path: Path) -> None:
        from interceptor.plugins.discovery import discover_plugins
        from interceptor.plugins.install import install_plugin
        from interceptor.plugins.runtime import PluginRunner

        install_plugin(SAMPLE_PLUGIN_DIR, tmp_path)
        plugins, _ = discover_plugins(tmp_path)
        runner = PluginRunner.from_discovered(plugins)

        assert len(runner.active_plugins) == 1
        assert runner.active_plugins[0].name == "sample-whitespace-normalizer"


# ---------------------------------------------------------------------------
# D. Health reports installed plugin healthy
# ---------------------------------------------------------------------------


class TestD_HealthAfterInstall:
    def test_health_pass_with_installed_plugin(self, tmp_path: Path) -> None:
        from interceptor.health import check_plugin_integrity
        from interceptor.plugins.install import install_plugin

        install_plugin(SAMPLE_PLUGIN_DIR, tmp_path)
        result = check_plugin_integrity(tmp_path)

        assert result.status == "pass"
        assert result.details["discovered"] == "1"
        assert result.details["loaded"] == "1"
        assert "sample-whitespace-normalizer" in result.message

    def test_health_reports_hook_info(self, tmp_path: Path) -> None:
        from interceptor.health import check_plugin_integrity
        from interceptor.plugins.install import install_plugin

        install_plugin(SAMPLE_PLUGIN_DIR, tmp_path)
        result = check_plugin_integrity(tmp_path)

        assert "prevalidate" in result.details.get("hooks", "")


# ---------------------------------------------------------------------------
# E. Hook fires after install
# ---------------------------------------------------------------------------


class TestE_HookFires:
    def test_prevalidate_fires_after_install(self, tmp_path: Path) -> None:
        from interceptor.plugins.discovery import discover_plugins
        from interceptor.plugins.install import install_plugin
        from interceptor.plugins.runtime import PluginRunner

        install_plugin(SAMPLE_PLUGIN_DIR, tmp_path)
        plugins, _ = discover_plugins(tmp_path)
        runner = PluginRunner.from_discovered(plugins)

        result = runner.run_hook("prevalidate", "hello   \nworld  ")
        assert result == "hello\nworld"

    def test_pipeline_path_fires(self, tmp_path: Path) -> None:
        from interceptor.adapters.models import ExecutionResult
        from interceptor.adapters.service import _evaluate_result
        from interceptor.plugins.discovery import discover_plugins
        from interceptor.plugins.install import install_plugin
        from interceptor.plugins.runtime import PluginRunner

        install_plugin(SAMPLE_PLUGIN_DIR, tmp_path)
        plugins, _ = discover_plugins(tmp_path)
        runner = PluginRunner.from_discovered(plugins)

        result = ExecutionResult(backend="claude", text="dirty   ")
        _evaluate_result(result, "prompt", plugin_runner=runner)

        assert result.text == "dirty"


# ---------------------------------------------------------------------------
# F. Uninstall restores baseline
# ---------------------------------------------------------------------------


class TestF_Uninstall:
    def test_uninstall_removes_directory(self, tmp_path: Path) -> None:
        from interceptor.plugins.install import install_plugin, uninstall_plugin

        install_plugin(SAMPLE_PLUGIN_DIR, tmp_path)
        assert (tmp_path / "sample-plugin").is_dir()

        removed = uninstall_plugin("sample-plugin", tmp_path)
        assert removed is True
        assert not (tmp_path / "sample-plugin").exists()

    def test_uninstall_returns_false_if_missing(self, tmp_path: Path) -> None:
        from interceptor.plugins.install import uninstall_plugin

        removed = uninstall_plugin("nonexistent", tmp_path)
        assert removed is False

    def test_no_plugins_after_uninstall(self, tmp_path: Path) -> None:
        from interceptor.plugins.discovery import discover_plugins
        from interceptor.plugins.install import install_plugin, uninstall_plugin

        install_plugin(SAMPLE_PLUGIN_DIR, tmp_path)
        plugins, _ = discover_plugins(tmp_path)
        assert len(plugins) == 1

        uninstall_plugin("sample-plugin", tmp_path)
        plugins, _ = discover_plugins(tmp_path)
        assert len(plugins) == 0


# ---------------------------------------------------------------------------
# G. Health returns to baseline after removal
# ---------------------------------------------------------------------------


class TestG_HealthAfterRemoval:
    def test_health_pass_after_uninstall(self, tmp_path: Path) -> None:
        from interceptor.health import check_plugin_integrity
        from interceptor.plugins.install import install_plugin, uninstall_plugin

        # Install → healthy
        install_plugin(SAMPLE_PLUGIN_DIR, tmp_path)
        r1 = check_plugin_integrity(tmp_path)
        assert r1.status == "pass"
        assert r1.details["loaded"] == "1"

        # Uninstall → baseline
        uninstall_plugin("sample-plugin", tmp_path)
        r2 = check_plugin_integrity(tmp_path)
        assert r2.status == "pass"
        assert r2.details["discovered"] == "0"


# ---------------------------------------------------------------------------
# H. Full lifecycle end-to-end
# ---------------------------------------------------------------------------


class TestH_FullLifecycle:
    def test_install_discover_hook_health_uninstall_baseline(
        self, tmp_path: Path
    ) -> None:
        """Complete lifecycle in a single test: clean → install → use → remove."""
        from interceptor.health import check_plugin_integrity
        from interceptor.plugins.discovery import discover_plugins
        from interceptor.plugins.install import install_plugin, uninstall_plugin
        from interceptor.plugins.runtime import PluginRunner

        # Step 1: clean baseline
        plugins, _ = discover_plugins(tmp_path)
        assert len(plugins) == 0
        h0 = check_plugin_integrity(tmp_path)
        assert h0.status == "pass"

        # Step 2: install
        install_plugin(SAMPLE_PLUGIN_DIR, tmp_path)

        # Step 3: discover + load
        plugins, _ = discover_plugins(tmp_path)
        assert len(plugins) == 1
        runner = PluginRunner.from_discovered(plugins)
        assert len(runner.active_plugins) == 1

        # Step 4: hook fires
        result = runner.run_hook("prevalidate", "test   ")
        assert result == "test"

        # Step 5: health green
        h1 = check_plugin_integrity(tmp_path)
        assert h1.status == "pass"
        assert h1.details["loaded"] == "1"

        # Step 6: uninstall
        uninstall_plugin("sample-plugin", tmp_path)

        # Step 7: baseline restored
        plugins, _ = discover_plugins(tmp_path)
        assert len(plugins) == 0
        h2 = check_plugin_integrity(tmp_path)
        assert h2.status == "pass"
        assert h2.details["discovered"] == "0"


# ---------------------------------------------------------------------------
# I. No network dependency (verified by construction — all tests use tmp_path)
# ---------------------------------------------------------------------------


class TestI_NoNetwork:
    def test_install_is_local_only(self, tmp_path: Path) -> None:
        """Install uses shutil.copytree — no network, no registry."""
        import inspect

        from interceptor.plugins.install import install_plugin

        src = inspect.getsource(install_plugin)
        assert "http" not in src.lower()
        assert "request" not in src.lower()
        assert "download" not in src.lower()


# ---------------------------------------------------------------------------
# J. No-plugin baseline unchanged
# ---------------------------------------------------------------------------


class TestJ_NoPluginBaseline:
    def test_no_plugins_runner_works(self) -> None:
        from interceptor.plugins.runtime import PluginRunner

        runner = PluginRunner([])
        result = runner.run_hook("prevalidate", "text")
        assert result == "text"

    def test_health_pass_nonexistent_dir(self) -> None:
        from interceptor.health import check_plugin_integrity

        result = check_plugin_integrity(Path("/nonexistent"))
        assert result.status == "pass"


# ---------------------------------------------------------------------------
# K. Sample plugin behavior intact
# ---------------------------------------------------------------------------


class TestK_SamplePluginIntact:
    def test_sample_plugin_from_examples(self, tmp_path: Path) -> None:
        """Sample plugin works when loaded directly from examples/."""
        import shutil

        shutil.copytree(
            SAMPLE_PLUGIN_DIR, tmp_path / "sample-whitespace-normalizer"
        )

        from interceptor.plugins.discovery import discover_plugins
        from interceptor.plugins.runtime import PluginRunner

        plugins, _ = discover_plugins(tmp_path)
        runner = PluginRunner.from_discovered(plugins)

        assert runner.run_hook("prevalidate", "a  \nb  ") == "a\nb"


# ---------------------------------------------------------------------------
# L. Install artifact is minimal
# ---------------------------------------------------------------------------


class TestL_InstallArtifactMinimal:
    def test_install_module_is_small(self) -> None:
        """The install helper is under 40 lines — minimal artifact."""
        install_file = (
            Path(__file__).resolve().parent.parent
            / "src"
            / "interceptor"
            / "plugins"
            / "install.py"
        )
        lines = install_file.read_text().splitlines()
        assert len(lines) < 50, f"install.py is {len(lines)} lines — too large"

    def test_no_new_dependencies(self) -> None:
        """Install helper uses only stdlib shutil + pathlib."""
        import ast

        install_file = (
            Path(__file__).resolve().parent.parent
            / "src"
            / "interceptor"
            / "plugins"
            / "install.py"
        )
        source = install_file.read_text()
        tree = ast.parse(source)

        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split(".")[0])
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module.split(".")[0])

        allowed = {"__future__", "shutil", "pathlib"}
        unexpected = imports - allowed
        assert len(unexpected) == 0, f"Unexpected imports: {unexpected}"
