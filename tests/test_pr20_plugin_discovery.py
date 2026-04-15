"""PR-20 tests — plugin discovery, manifest validation, registry, and CLI."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
from typer.testing import CliRunner

from interceptor.plugins.discovery import discover_plugins, load_plugin_manifest
from interceptor.plugins.models import (
    VALID_HOOKS_V1,
    DiscoveredPlugin,
    PluginManifest,
)
from interceptor.plugins.registry import PluginRegistry


def _write_manifest(plugin_dir: Path, content: str) -> Path:
    """Write a plugin.toml into *plugin_dir* and return the directory."""
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.toml").write_text(textwrap.dedent(content), encoding="utf-8")
    return plugin_dir


_VALID_TOML = """\
name = "alpha"
version = "1.0.0"
description = "A test plugin"
author = "Test Author"
hooks = ["preroute", "postcompile"]
api_version = "v1"
min_compiler_version = "0.1.0"
max_compiler_version = "2.0.0"
"""


# ── A: Valid plugin manifest loads ───────────────────────────────────
class TestA_ValidManifest:
    def test_valid_manifest_loads(self, tmp_path: Path) -> None:
        d = _write_manifest(tmp_path / "alpha", _VALID_TOML)
        m = load_plugin_manifest(d)
        assert m is not None
        assert m.name == "alpha"
        assert m.version == "1.0.0"
        assert m.hooks == ["preroute", "postcompile"]
        assert m.api_version == "v1"
        assert m.min_compiler_version == "0.1.0"
        assert m.max_compiler_version == "2.0.0"
        assert m.author == "Test Author"
        assert m.description == "A test plugin"

    def test_optional_fields_default_none(self, tmp_path: Path) -> None:
        toml = """\
        name = "bare"
        version = "0.1.0"
        description = "Minimal"
        hooks = ["presend"]
        api_version = "v1"
        min_compiler_version = "0.1.0"
        max_compiler_version = "1.0.0"
        """
        d = _write_manifest(tmp_path / "bare", toml)
        m = load_plugin_manifest(d)
        assert m is not None
        assert m.author is None
        assert m.config is None
        assert m.permissions is None

    def test_config_and_permissions_load(self, tmp_path: Path) -> None:
        toml = """\
        name = "full"
        version = "1.0.0"
        description = "Full plugin"
        hooks = ["preroute"]
        api_version = "v1"
        min_compiler_version = "0.1.0"
        max_compiler_version = "1.0.0"

        [config]
        threshold = 0.8

        [permissions]
        network = true
        """
        d = _write_manifest(tmp_path / "full", toml)
        m = load_plugin_manifest(d)
        assert m is not None
        assert m.config == {"threshold": 0.8}
        assert m.permissions == {"network": True}


# ── B: Missing plugin.toml skipped ──────────────────────────────────
class TestB_MissingToml:
    def test_missing_toml_returns_none(self, tmp_path: Path) -> None:
        d = tmp_path / "no-manifest"
        d.mkdir()
        assert load_plugin_manifest(d) is None

    def test_missing_toml_skipped_in_discovery(self, tmp_path: Path) -> None:
        (tmp_path / "empty-plugin").mkdir()
        plugins, warnings = discover_plugins(tmp_path)
        assert plugins == []
        assert len(warnings) == 1
        assert "empty-plugin" in warnings[0]


# ── C: Malformed TOML skipped ───────────────────────────────────────
class TestC_MalformedToml:
    def test_malformed_toml_returns_none(self, tmp_path: Path) -> None:
        d = tmp_path / "broken"
        d.mkdir()
        (d / "plugin.toml").write_text("not = [valid toml {{", encoding="utf-8")
        assert load_plugin_manifest(d) is None

    def test_malformed_toml_skipped_in_discovery(self, tmp_path: Path) -> None:
        d = tmp_path / "broken"
        d.mkdir()
        (d / "plugin.toml").write_text("[[[bad", encoding="utf-8")
        plugins, warnings = discover_plugins(tmp_path)
        assert plugins == []
        assert len(warnings) == 1
        assert "broken" in warnings[0]


# ── D: Invalid hook name skipped ────────────────────────────────────
class TestD_InvalidHook:
    def test_invalid_hook_rejects(self, tmp_path: Path) -> None:
        toml = """\
        name = "bad-hook"
        version = "1.0.0"
        description = "Bad hook"
        hooks = ["preroute", "on_crash"]
        api_version = "v1"
        min_compiler_version = "0.1.0"
        max_compiler_version = "1.0.0"
        """
        d = _write_manifest(tmp_path / "bad-hook", toml)
        assert load_plugin_manifest(d) is None

    def test_all_valid_hooks_accepted(self, tmp_path: Path) -> None:
        hooks_str = ", ".join(f'"{h}"' for h in sorted(VALID_HOOKS_V1))
        toml = f"""\
name = "all-hooks"
version = "1.0.0"
description = "All hooks"
hooks = [{hooks_str}]
api_version = "v1"
min_compiler_version = "0.1.0"
max_compiler_version = "1.0.0"
"""
        d = _write_manifest(tmp_path / "all-hooks", toml)
        m = load_plugin_manifest(d)
        assert m is not None
        assert len(m.hooks) == len(VALID_HOOKS_V1)


# ── E: Missing required field skipped ────────────────────────────────
class TestE_MissingField:
    @pytest.mark.parametrize("field", [
        "name", "version", "description", "hooks",
        "api_version", "min_compiler_version", "max_compiler_version",
    ])
    def test_missing_required_field(self, tmp_path: Path, field: str) -> None:
        lines = [
            'name = "x"',
            'version = "1.0.0"',
            'description = "x"',
            'hooks = ["preroute"]',
            'api_version = "v1"',
            'min_compiler_version = "0.1.0"',
            'max_compiler_version = "1.0.0"',
        ]
        filtered = [ln for ln in lines if not ln.startswith(f"{field} =")]
        d = _write_manifest(tmp_path / f"no-{field}", "\n".join(filtered))
        assert load_plugin_manifest(d) is None


# ── F: api_version other than v1 skipped ─────────────────────────────
class TestF_BadApiVersion:
    def test_api_version_v2_rejected(self, tmp_path: Path) -> None:
        toml = """\
        name = "v2-plugin"
        version = "1.0.0"
        description = "Wrong api"
        hooks = ["preroute"]
        api_version = "v2"
        min_compiler_version = "0.1.0"
        max_compiler_version = "1.0.0"
        """
        d = _write_manifest(tmp_path / "v2", toml)
        assert load_plugin_manifest(d) is None

    def test_empty_api_version_rejected(self, tmp_path: Path) -> None:
        toml = """\
        name = "empty-api"
        version = "1.0.0"
        description = "Empty api"
        hooks = ["preroute"]
        api_version = ""
        min_compiler_version = "0.1.0"
        max_compiler_version = "1.0.0"
        """
        d = _write_manifest(tmp_path / "empty-api", toml)
        assert load_plugin_manifest(d) is None


# ── G: Multiple valid plugins discovered ─────────────────────────────
class TestG_MultipleValid:
    def test_multiple_plugins_discovered(self, tmp_path: Path) -> None:
        for name in ("alpha", "beta", "gamma"):
            toml = f"""\
name = "{name}"
version = "1.0.0"
description = "{name} plugin"
hooks = ["preroute"]
api_version = "v1"
min_compiler_version = "0.1.0"
max_compiler_version = "1.0.0"
"""
            _write_manifest(tmp_path / name, toml)

        plugins, warnings = discover_plugins(tmp_path)
        assert len(plugins) == 3
        assert warnings == []
        names = [p.manifest.name for p in plugins]
        assert set(names) == {"alpha", "beta", "gamma"}


# ── H: Invalid + valid mixed directory ───────────────────────────────
class TestH_MixedDirectory:
    def test_mixed_valid_and_invalid(self, tmp_path: Path) -> None:
        _write_manifest(tmp_path / "good", _VALID_TOML)
        bad = tmp_path / "bad"
        bad.mkdir()
        (bad / "plugin.toml").write_text("garbage {{", encoding="utf-8")
        _write_manifest(tmp_path / "no-name", """\
        version = "1.0.0"
        description = "missing name"
        hooks = ["preroute"]
        api_version = "v1"
        min_compiler_version = "0.1.0"
        max_compiler_version = "1.0.0"
        """)

        plugins, warnings = discover_plugins(tmp_path)
        assert len(plugins) == 1
        assert plugins[0].manifest.name == "alpha"
        assert len(warnings) == 2


# ── I: Non-directory children ignored ────────────────────────────────
class TestI_NonDirectory:
    def test_files_in_plugins_dir_ignored(self, tmp_path: Path) -> None:
        _write_manifest(tmp_path / "good", _VALID_TOML)
        (tmp_path / "README.md").write_text("notes", encoding="utf-8")
        (tmp_path / ".hidden").write_text("x", encoding="utf-8")

        plugins, warnings = discover_plugins(tmp_path)
        assert len(plugins) == 1
        assert warnings == []


# ── J: Nested directories not recursed into ──────────────────────────
class TestJ_NoRecursion:
    def test_nested_dirs_not_recursed(self, tmp_path: Path) -> None:
        outer = tmp_path / "outer"
        _write_manifest(outer, _VALID_TOML)
        inner = outer / "inner-plugin"
        _write_manifest(inner, _VALID_TOML.replace('"alpha"', '"inner"'))

        plugins, warnings = discover_plugins(tmp_path)
        assert len(plugins) == 1
        assert plugins[0].manifest.name == "alpha"


# ── K: Registry get/list/count works ─────────────────────────────────
class TestK_Registry:
    def test_registry_operations(self, tmp_path: Path) -> None:
        for name in ("x-ray", "yankee", "zulu"):
            toml = f"""\
name = "{name}"
version = "1.0.0"
description = "{name}"
hooks = ["preroute"]
api_version = "v1"
min_compiler_version = "0.1.0"
max_compiler_version = "1.0.0"
"""
            _write_manifest(tmp_path / name, toml)

        reg = PluginRegistry.load_all(tmp_path)
        assert reg.count() == 3
        assert len(reg.list_all()) == 3
        assert reg.list_all()[0].manifest.name == "x-ray"
        assert reg.get("yankee") is not None
        assert reg.get("yankee").manifest.name == "yankee"
        assert reg.get("nonexistent") is None

    def test_empty_registry(self, tmp_path: Path) -> None:
        reg = PluginRegistry.load_all(tmp_path)
        assert reg.count() == 0
        assert reg.list_all() == []
        assert reg.get("anything") is None
        assert reg.warnings == []

    def test_missing_dir_registry(self, tmp_path: Path) -> None:
        reg = PluginRegistry.load_all(tmp_path / "nonexistent")
        assert reg.count() == 0
        assert reg.warnings == []


# ── L: Duplicate plugin names handled ────────────────────────────────
class TestL_DuplicateNames:
    def test_first_wins_duplicate_skipped(self, tmp_path: Path) -> None:
        _write_manifest(tmp_path / "aaa-first", _VALID_TOML)
        _write_manifest(
            tmp_path / "zzz-second",
            _VALID_TOML.replace('version = "1.0.0"', 'version = "2.0.0"'),
        )

        plugins, warnings = discover_plugins(tmp_path)
        assert len(plugins) == 1
        assert plugins[0].manifest.version == "1.0.0"
        assert len(warnings) == 1
        assert "duplicate" in warnings[0].lower()


# ── M: CLI mycli plugins renders discovered plugins ──────────────────
class TestM_CliPlugins:
    def test_cli_plugins_table(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_manifest(tmp_path / "demo", _VALID_TOML)
        monkeypatch.setattr("interceptor.cli.PLUGINS_DIR", tmp_path, raising=False)
        from interceptor.constants import PLUGINS_DIR  # noqa: F401

        monkeypatch.setattr("interceptor.constants.PLUGINS_DIR", tmp_path)

        from interceptor.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["plugins"])
        assert result.exit_code == 0
        assert "alpha" in result.output
        assert "1.0.0" in result.output

    def test_cli_plugins_json(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_manifest(tmp_path / "demo", _VALID_TOML)
        monkeypatch.setattr("interceptor.constants.PLUGINS_DIR", tmp_path)

        from interceptor.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["plugins", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["name"] == "alpha"
        assert data[0]["hooks"] == ["preroute", "postcompile"]


# ── N: CLI zero-plugins behavior ─────────────────────────────────────
class TestN_CliZeroPlugins:
    def test_cli_no_plugins(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("interceptor.constants.PLUGINS_DIR", tmp_path)

        from interceptor.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["plugins"])
        assert result.exit_code == 0
        assert "No plugins discovered" in result.output

    def test_cli_no_plugins_json(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("interceptor.constants.PLUGINS_DIR", tmp_path)

        from interceptor.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["plugins", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == []


# ── O: Regression safety ─────────────────────────────────────────────
class TestO_Regression:
    def test_health(self) -> None:
        from interceptor.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["health"])
        assert result.exit_code == 0

    def test_version(self) -> None:
        from interceptor.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0

    def test_templates(self) -> None:
        from interceptor.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["templates"])
        assert result.exit_code == 0

    def test_logs(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("interceptor.constants.LOG_DIR", tmp_path)

        from interceptor.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["logs"])
        assert result.exit_code == 0

    def test_stats(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("interceptor.constants.LOG_DIR", tmp_path)

        from interceptor.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0


# ── P: Empty compiler version rejected ───────────────────────────────
class TestP_EmptyVersionStrings:
    def test_empty_min_compiler_version(self, tmp_path: Path) -> None:
        toml = """\
        name = "empty-min"
        version = "1.0.0"
        description = "empty min"
        hooks = ["preroute"]
        api_version = "v1"
        min_compiler_version = ""
        max_compiler_version = "1.0.0"
        """
        d = _write_manifest(tmp_path / "empty-min", toml)
        assert load_plugin_manifest(d) is None

    def test_empty_max_compiler_version(self, tmp_path: Path) -> None:
        toml = """\
        name = "empty-max"
        version = "1.0.0"
        description = "empty max"
        hooks = ["preroute"]
        api_version = "v1"
        min_compiler_version = "0.1.0"
        max_compiler_version = ""
        """
        d = _write_manifest(tmp_path / "empty-max", toml)
        assert load_plugin_manifest(d) is None

    def test_whitespace_only_version_rejected(self, tmp_path: Path) -> None:
        toml = """\
        name = "ws"
        version = "1.0.0"
        description = "whitespace"
        hooks = ["preroute"]
        api_version = "v1"
        min_compiler_version = "   "
        max_compiler_version = "1.0.0"
        """
        d = _write_manifest(tmp_path / "ws", toml)
        assert load_plugin_manifest(d) is None


# ── Q: Extra fields ignored ──────────────────────────────────────────
class TestQ_ExtraFields:
    def test_extra_toml_fields_ignored(self, tmp_path: Path) -> None:
        toml = """\
        name = "extra"
        version = "1.0.0"
        description = "Has extra"
        hooks = ["preroute"]
        api_version = "v1"
        min_compiler_version = "0.1.0"
        max_compiler_version = "1.0.0"
        future_field = "ignored"
        """
        d = _write_manifest(tmp_path / "extra", toml)
        m = load_plugin_manifest(d)
        assert m is not None
        assert m.name == "extra"


# ── R: Empty hooks list accepted ─────────────────────────────────────
class TestR_EmptyHooks:
    def test_empty_hooks_valid(self, tmp_path: Path) -> None:
        toml = """\
        name = "no-hooks"
        version = "1.0.0"
        description = "No hooks"
        hooks = []
        api_version = "v1"
        min_compiler_version = "0.1.0"
        max_compiler_version = "1.0.0"
        """
        d = _write_manifest(tmp_path / "no-hooks", toml)
        m = load_plugin_manifest(d)
        assert m is not None
        assert m.hooks == []
