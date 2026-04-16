"""Tests for interceptor.cli — CLI smoke tests via CliRunner."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from interceptor.cli import app

runner = CliRunner()


class TestVersion:
    def test_prints_version(self) -> None:
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "1.3.0" in result.output


class TestHelp:
    def test_help_exits_zero(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Prompt Compiler" in result.output


class TestHealthCommand:
    def test_health_default_exits_zero(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        config = tmp_path / "config.toml"
        config.write_text('[general]\nbackend = "claude"\n', encoding="utf-8")
        monkeypatch.setattr(
            "interceptor.health.CONFIG_FILE", config
        )
        result = runner.invoke(app, ["health"])
        assert result.exit_code == 0
        assert "config_valid" in result.output

    def test_health_check_specific(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        config = tmp_path / "config.toml"
        config.write_text('[general]\nbackend = "claude"\n', encoding="utf-8")
        monkeypatch.setattr(
            "interceptor.health.CONFIG_FILE", config
        )
        result = runner.invoke(app, ["health", "--check", "config_valid"])
        assert result.exit_code == 0
        assert "pass" in result.output.lower() or "✅" in result.output

    def test_health_unknown_check_exits_one(self) -> None:
        result = runner.invoke(app, ["health", "--check", "nonexistent"])
        assert result.exit_code == 1
        assert "unknown" in result.output.lower()

    def test_health_warn_exits_zero_normal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "interceptor.health.CONFIG_FILE",
            tmp_path / "missing.toml",
        )
        result = runner.invoke(app, ["health"])
        assert result.exit_code == 0
        assert "warn" in result.output.lower() or "⚠" in result.output

    def test_health_strict_exits_one_on_warn(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "interceptor.health.CONFIG_FILE",
            tmp_path / "missing.toml",
        )
        result = runner.invoke(app, ["health", "--strict"])
        assert result.exit_code == 1
