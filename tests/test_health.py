"""Tests for interceptor.health — config validation check."""

from __future__ import annotations

from pathlib import Path

from interceptor.health import check_config_valid


class TestCheckConfigValid:
    def test_valid_config_passes(self, valid_toml: Path) -> None:
        result = check_config_valid(valid_toml)
        assert result.status == "pass"
        assert result.name == "config_valid"

    def test_missing_config_warns(self, tmp_path: Path) -> None:
        result = check_config_valid(tmp_path / "nonexistent.toml")
        assert result.status == "warn"
        assert "defaults" in result.message.lower()

    def test_invalid_toml_warns(self, invalid_toml: Path) -> None:
        result = check_config_valid(invalid_toml)
        assert result.status == "warn"
        assert "parse" in result.message.lower() or "toml" in result.message.lower()

    def test_bad_values_warns(self, bad_values_toml: Path) -> None:
        result = check_config_valid(bad_values_toml)
        assert result.status == "warn"
        assert "error" in result.message.lower()

    def test_result_includes_path(self, valid_toml: Path) -> None:
        result = check_config_valid(valid_toml)
        assert "path" in result.details
        assert str(valid_toml) in result.details["path"]

    def test_unreadable_file_warns(self, tmp_config_dir: Path) -> None:
        f = tmp_config_dir / "config.toml"
        f.write_text("valid = true", encoding="utf-8")
        f.chmod(0o000)
        result = check_config_valid(f)
        assert result.status == "warn"
        f.chmod(0o644)
