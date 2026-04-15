"""PR-26 — Plugin health/status reporting in ``mycli health``.

Tests: A through L covering healthy, absent, degraded, JSON, strict,
focused check, hook mismatch, malformed state, and regression safety.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
from typer.testing import CliRunner

from interceptor.cli import app
from interceptor.health import HealthCheckResult, check_plugin_integrity

runner = CliRunner()

# ---------------------------------------------------------------------------
# Helpers — write minimal plugin fixtures to tmp dirs
# ---------------------------------------------------------------------------

_VALID_MANIFEST = """\
name = "{name}"
version = "1.0.0"
description = "test plugin"
hooks = [{hooks}]
api_version = "v1"
min_compiler_version = "0.1.0"
max_compiler_version = "99.0.0"
"""

_VALID_PLUGIN_PY = """\
class Plugin:
{methods}
"""


def _write_plugin(
    plugins_dir: Path,
    name: str,
    hooks: list[str],
    *,
    broken_manifest: bool = False,
    missing_py: bool = False,
    missing_hook_method: str | None = None,
    crash_init: bool = False,
) -> Path:
    """Write a minimal plugin fixture and return the plugin dir."""
    pdir = plugins_dir / name
    pdir.mkdir(parents=True, exist_ok=True)

    if broken_manifest:
        (pdir / "plugin.toml").write_text("not valid [[[ toml", encoding="utf-8")
        (pdir / "plugin.py").write_text("class Plugin: pass", encoding="utf-8")
        return pdir

    hook_list = ", ".join(f'"{h}"' for h in hooks)
    (pdir / "plugin.toml").write_text(
        _VALID_MANIFEST.format(name=name, hooks=hook_list), encoding="utf-8"
    )

    if missing_py:
        return pdir

    if crash_init:
        (pdir / "plugin.py").write_text(
            "class Plugin:\n    def __init__(self): raise RuntimeError('boom')\n",
            encoding="utf-8",
        )
        return pdir

    methods: list[str] = []
    for h in hooks:
        if h == missing_hook_method:
            continue
        methods.append(f"    def {h}(self, data, *a): return data")

    if not methods:
        methods.append("    pass")

    (pdir / "plugin.py").write_text(
        _VALID_PLUGIN_PY.format(methods="\n".join(methods)), encoding="utf-8"
    )
    return pdir


# ===================================================================
# A. No plugins directory → healthy
# ===================================================================


class TestA_NoPluginsDir:
    def test_no_dir_passes(self, tmp_path: Path) -> None:
        result = check_plugin_integrity(tmp_path / "nonexistent")
        assert result.status == "pass"
        assert result.name == "plugin_integrity"
        assert "inactive" in result.message.lower() or "no plugins" in result.message.lower()

    def test_no_dir_details(self, tmp_path: Path) -> None:
        result = check_plugin_integrity(tmp_path / "nonexistent")
        assert result.details["discovered"] == "0"
        assert result.details["loaded"] == "0"


# ===================================================================
# B. Empty plugins directory → healthy
# ===================================================================


class TestB_EmptyDir:
    def test_empty_dir_passes(self, tmp_path: Path) -> None:
        pdir = tmp_path / "plugins"
        pdir.mkdir()
        result = check_plugin_integrity(pdir)
        assert result.status == "pass"
        assert "no plugins" in result.message.lower()


# ===================================================================
# C. Healthy plugins → pass with hook info
# ===================================================================


class TestC_HealthyPlugins:
    def test_single_healthy(self, tmp_path: Path) -> None:
        pdir = tmp_path / "plugins"
        _write_plugin(pdir, "alpha", ["presend", "postreceive"])
        result = check_plugin_integrity(pdir)
        assert result.status == "pass"
        assert "alpha" in result.message
        assert result.details["loaded"] == "1"

    def test_multiple_healthy(self, tmp_path: Path) -> None:
        pdir = tmp_path / "plugins"
        _write_plugin(pdir, "alpha", ["presend"])
        _write_plugin(pdir, "beta", ["precompile", "postcompile"])
        result = check_plugin_integrity(pdir)
        assert result.status == "pass"
        assert result.details["loaded"] == "2"
        assert "alpha" in result.message
        assert "beta" in result.message

    def test_hooks_in_details(self, tmp_path: Path) -> None:
        pdir = tmp_path / "plugins"
        _write_plugin(pdir, "alpha", ["presend", "postreceive"])
        result = check_plugin_integrity(pdir)
        assert "hooks" in result.details
        assert "presend" in result.details["hooks"]
        assert "postreceive" in result.details["hooks"]


# ===================================================================
# D. Broken manifest → warn (soft-fail)
# ===================================================================


class TestD_BrokenManifest:
    def test_broken_manifest_warns(self, tmp_path: Path) -> None:
        pdir = tmp_path / "plugins"
        _write_plugin(pdir, "broken", ["presend"], broken_manifest=True)
        result = check_plugin_integrity(pdir)
        assert result.status == "warn"
        assert "discovery_warnings" in result.details or "failed" in result.details

    def test_missing_plugin_py_warns(self, tmp_path: Path) -> None:
        pdir = tmp_path / "plugins"
        _write_plugin(pdir, "nopy", ["presend"], missing_py=True)
        result = check_plugin_integrity(pdir)
        assert result.status == "warn"
        assert result.details.get("failed_plugins") == "nopy"


# ===================================================================
# E. Mixed — one broken among healthy → degraded, not total failure
# ===================================================================


class TestE_MixedPlugins:
    def test_mixed_is_warn(self, tmp_path: Path) -> None:
        pdir = tmp_path / "plugins"
        _write_plugin(pdir, "good", ["presend"])
        _write_plugin(pdir, "bad", ["presend"], broken_manifest=True)
        result = check_plugin_integrity(pdir)
        assert result.status == "warn"
        assert result.details["loaded"] == "1"
        assert "degraded" in result.message.lower()

    def test_good_plugin_still_reported(self, tmp_path: Path) -> None:
        pdir = tmp_path / "plugins"
        _write_plugin(pdir, "good", ["presend"])
        _write_plugin(pdir, "bad", ["presend"], crash_init=True)
        result = check_plugin_integrity(pdir)
        assert result.status == "warn"
        assert "hooks" in result.details
        assert "good" in result.details["hooks"]


# ===================================================================
# F. Human-readable output — plugin info in table
# ===================================================================


class TestF_HumanOutput:
    def test_health_table_shows_plugin_integrity(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pdir = tmp_path / "plugins"
        _write_plugin(pdir, "alpha", ["presend"])
        monkeypatch.setattr("interceptor.constants.PLUGINS_DIR", pdir)
        result = runner.invoke(app, ["health", "--check", "plugin_integrity"])
        assert result.exit_code == 0
        assert "plugin_integrity" in result.stdout

    def test_full_health_includes_plugins(self) -> None:
        result = runner.invoke(app, ["health"])
        assert "plugin_integrity" in result.stdout


# ===================================================================
# G. JSON output — structured plugin health
# ===================================================================


class TestG_JsonOutput:
    def test_json_flag(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pdir = tmp_path / "plugins"
        _write_plugin(pdir, "alpha", ["presend"])
        monkeypatch.setattr("interceptor.constants.PLUGINS_DIR", pdir)
        result = runner.invoke(
            app, ["health", "--json", "--check", "plugin_integrity"],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "overall" in data
        assert "checks" in data
        assert data["checks"][0]["name"] == "plugin_integrity"
        assert data["checks"][0]["status"] == "pass"
        assert "details" in data["checks"][0]

    def test_json_overall_warn(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pdir = tmp_path / "plugins"
        _write_plugin(pdir, "bad", ["presend"], broken_manifest=True)
        monkeypatch.setattr("interceptor.constants.PLUGINS_DIR", pdir)
        result = runner.invoke(
            app, ["health", "--json", "--check", "plugin_integrity"],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["overall"] == "warn"
        assert data["checks"][0]["status"] == "warn"

    def test_json_no_plugins(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("interceptor.constants.PLUGINS_DIR", tmp_path / "empty")
        result = runner.invoke(
            app, ["health", "--json", "--check", "plugin_integrity"],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["overall"] == "pass"


# ===================================================================
# H. Focused check — --check plugin_integrity
# ===================================================================


class TestH_FocusedCheck:
    def test_focused_check_works(self) -> None:
        result = runner.invoke(app, ["health", "--check", "plugin_integrity"])
        assert result.exit_code == 0
        assert "plugin_integrity" in result.stdout

    def test_unknown_check_fails(self) -> None:
        result = runner.invoke(app, ["health", "--check", "nonexistent"])
        assert result.exit_code == 1


# ===================================================================
# I. Strict mode — warn escalates to exit 1
# ===================================================================


class TestI_StrictMode:
    def test_strict_escalates_warn(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pdir = tmp_path / "plugins"
        _write_plugin(pdir, "bad", ["presend"], broken_manifest=True)
        monkeypatch.setattr("interceptor.constants.PLUGINS_DIR", pdir)
        result = runner.invoke(
            app, ["health", "--strict", "--check", "plugin_integrity"],
        )
        assert result.exit_code == 1

    def test_strict_pass_exits_0(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pdir = tmp_path / "plugins"
        _write_plugin(pdir, "good", ["presend"])
        monkeypatch.setattr("interceptor.constants.PLUGINS_DIR", pdir)
        result = runner.invoke(
            app, ["health", "--strict", "--check", "plugin_integrity"],
        )
        assert result.exit_code == 0


# ===================================================================
# J. Malformed state — never crashes
# ===================================================================


class TestJ_MalformedState:
    def test_dir_with_files_not_dirs(self, tmp_path: Path) -> None:
        pdir = tmp_path / "plugins"
        pdir.mkdir()
        (pdir / "not-a-dir.txt").write_text("hello")
        result = check_plugin_integrity(pdir)
        assert result.status == "pass"

    def test_empty_subdir(self, tmp_path: Path) -> None:
        pdir = tmp_path / "plugins"
        (pdir / "empty").mkdir(parents=True)
        result = check_plugin_integrity(pdir)
        assert result.status in ("pass", "warn")

    def test_plugin_init_crash(self, tmp_path: Path) -> None:
        pdir = tmp_path / "plugins"
        _write_plugin(pdir, "crashy", ["presend"], crash_init=True)
        result = check_plugin_integrity(pdir)
        assert result.status == "warn"
        assert "crashy" in result.details.get("failed_plugins", "")


# ===================================================================
# K. Non-plugin health regression
# ===================================================================


class TestK_Regression:
    def test_existing_checks_present(self) -> None:
        result = runner.invoke(app, ["health"])
        for name in ("config_valid", "templates_valid", "routing_valid",
                      "compilation_valid", "backends_valid"):
            assert name in result.stdout

    def test_existing_checks_still_run(self) -> None:
        result = runner.invoke(app, ["health", "--check", "config_valid"])
        assert result.exit_code in (0, 1)
        assert "config_valid" in result.stdout


# ===================================================================
# L. Hook mismatch — declared hook not callable
# ===================================================================


class TestL_HookMismatch:
    def test_missing_hook_method_warns(self, tmp_path: Path) -> None:
        pdir = tmp_path / "plugins"
        _write_plugin(
            pdir, "mismatch", ["presend", "postreceive"],
            missing_hook_method="postreceive",
        )
        result = check_plugin_integrity(pdir)
        assert result.status == "warn"
        assert "mismatch" in result.details.get("failed_plugins", "")
