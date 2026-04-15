"""Tests for interceptor.config — loading, merging, fallback, env overrides."""

from __future__ import annotations

from pathlib import Path

import pytest

from interceptor.config import Config, get_default_config, load_config


class TestGetDefaultConfig:
    def test_returns_config_instance(self) -> None:
        cfg = get_default_config()
        assert isinstance(cfg, Config)

    def test_default_backend_is_claude(self) -> None:
        cfg = get_default_config()
        assert cfg.general.backend == "claude"

    def test_default_routing_weights_sum_to_one(self) -> None:
        w = get_default_config().routing.weights
        assert abs(w.trigger + w.context + w.recency - 1.0) < 1e-9


class TestLoadConfigFromFile:
    def test_valid_toml_overrides_defaults(self, valid_toml: Path) -> None:
        cfg = load_config(valid_toml)
        assert cfg.general.backend == "openai"
        assert cfg.general.language == "ka"

    def test_valid_toml_keeps_unset_defaults(self, valid_toml: Path) -> None:
        cfg = load_config(valid_toml)
        assert cfg.general.env == "prod"
        assert cfg.routing.min_confidence == 0.55

    def test_missing_file_returns_defaults(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent.toml"
        cfg = load_config(missing)
        assert cfg == get_default_config()

    def test_invalid_toml_falls_back_to_defaults(
        self, invalid_toml: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cfg = load_config(invalid_toml)
        assert cfg.general.backend == "claude"
        captured = capsys.readouterr()
        assert "parse error" in captured.err.lower() or "toml" in captured.err.lower()

    def test_bad_values_falls_back_to_defaults(
        self, bad_values_toml: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cfg = load_config(bad_values_toml)
        assert cfg.routing.min_confidence == 0.55
        captured = capsys.readouterr()
        assert "validation error" in captured.err.lower() or "using defaults" in captured.err.lower()

    def test_partial_file_deep_merges(self, tmp_config_dir: Path) -> None:
        partial = tmp_config_dir / "config.toml"
        partial.write_text(
            '[routing.weights]\ntrigger = 0.50\n',
            encoding="utf-8",
        )
        cfg = load_config(partial)
        assert cfg.routing.weights.trigger == 0.50
        assert cfg.routing.weights.context == 0.25
        assert cfg.routing.weights.recency == 0.15


class TestEnvOverrides:
    def test_backend_override(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("INTERCEPTOR_BACKEND", "gemini")
        cfg = load_config(tmp_path / "missing.toml")
        assert cfg.general.backend == "gemini"

    def test_language_override(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("INTERCEPTOR_LANGUAGE", "ka")
        cfg = load_config(tmp_path / "missing.toml")
        assert cfg.general.language == "ka"

    def test_env_override(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("INTERCEPTOR_ENV", "dev")
        cfg = load_config(tmp_path / "missing.toml")
        assert cfg.general.env == "dev"

    def test_float_override(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("INTERCEPTOR_ROUTING_MIN_CONFIDENCE", "0.70")
        cfg = load_config(tmp_path / "missing.toml")
        assert cfg.routing.min_confidence == 0.70

    def test_env_wins_over_file(
        self, valid_toml: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("INTERCEPTOR_BACKEND", "gemini")
        cfg = load_config(valid_toml)
        assert cfg.general.backend == "gemini"


class TestExtraFieldsIgnored:
    def test_unknown_keys_ignored(self, tmp_config_dir: Path) -> None:
        f = tmp_config_dir / "config.toml"
        f.write_text(
            '[general]\nbackend = "claude"\nfuture_field = 42\n',
            encoding="utf-8",
        )
        cfg = load_config(f)
        assert cfg.general.backend == "claude"
