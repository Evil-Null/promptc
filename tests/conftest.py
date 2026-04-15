"""Shared fixtures for Prompt Compiler tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def tmp_config_dir(tmp_path: Path) -> Path:
    """Return a temporary directory usable as XDG_CONFIG_HOME/interceptor."""
    config_dir = tmp_path / "interceptor"
    config_dir.mkdir()
    return config_dir


@pytest.fixture()
def valid_toml(tmp_config_dir: Path) -> Path:
    """Write a valid minimal config.toml and return its path."""
    config_file = tmp_config_dir / "config.toml"
    config_file.write_text(
        '[general]\nbackend = "openai"\nlanguage = "ka"\n',
        encoding="utf-8",
    )
    return config_file


@pytest.fixture()
def invalid_toml(tmp_config_dir: Path) -> Path:
    """Write an unparseable TOML file and return its path."""
    config_file = tmp_config_dir / "config.toml"
    config_file.write_text("[[broken\nnot = valid toml", encoding="utf-8")
    return config_file


@pytest.fixture()
def bad_values_toml(tmp_config_dir: Path) -> Path:
    """Write TOML with wrong value types and return its path."""
    config_file = tmp_config_dir / "config.toml"
    config_file.write_text(
        '[routing]\nmin_confidence = "not_a_float"\n',
        encoding="utf-8",
    )
    return config_file
