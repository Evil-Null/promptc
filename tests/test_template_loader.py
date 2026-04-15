"""Tests for TOML template loader and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from interceptor.models.template import Template
from interceptor.template_loader import load_template, validate_template


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_VALID_TOML = """\
[meta]
name = "test-loader"
category = "ANALYTICAL"
version = "1.0.0"
author = "test"

[triggers]
en = ["analyze this"]
strength = "MEDIUM"

[prompt]
system_directive = "You are a test assistant."
chain_of_thought = "Think step by step."
output_schema = "Return JSON."

[quality_gates]
hard = ["Must be correct"]
soft = []

anti_patterns = ["Guessing"]
"""


@pytest.fixture()
def valid_toml_file(tmp_path: Path) -> Path:
    f = tmp_path / "valid.toml"
    f.write_text(_VALID_TOML, encoding="utf-8")
    return f


@pytest.fixture()
def broken_toml_file(tmp_path: Path) -> Path:
    f = tmp_path / "broken.toml"
    f.write_text("[[not valid\nfoo = bar", encoding="utf-8")
    return f


@pytest.fixture()
def missing_meta_toml(tmp_path: Path) -> Path:
    f = tmp_path / "no_meta.toml"
    f.write_text(
        '[triggers]\nen = ["x"]\n[prompt]\nsystem_directive = "y"\noutput_schema = "z"\n',
        encoding="utf-8",
    )
    return f


@pytest.fixture()
def invalid_category_toml(tmp_path: Path) -> Path:
    f = tmp_path / "bad_cat.toml"
    f.write_text(
        '[meta]\nname = "t"\ncategory = "INVALID"\nversion = "1"\nauthor = "x"\n'
        '[triggers]\nen = ["x"]\n'
        '[prompt]\nsystem_directive = "y"\noutput_schema = "z"\n',
        encoding="utf-8",
    )
    return f


@pytest.fixture()
def invalid_strength_toml(tmp_path: Path) -> Path:
    f = tmp_path / "bad_str.toml"
    f.write_text(
        '[meta]\nname = "t"\ncategory = "ANALYTICAL"\nversion = "1"\nauthor = "x"\n'
        '[triggers]\nen = ["x"]\nstrength = "ULTRA"\n'
        '[prompt]\nsystem_directive = "y"\noutput_schema = "z"\n',
        encoding="utf-8",
    )
    return f


# ---------------------------------------------------------------------------
# validate_template
# ---------------------------------------------------------------------------

def test_validate_valid_data() -> None:
    import tomllib

    data = tomllib.loads(_VALID_TOML)
    errors = validate_template(data)
    assert errors == []


def test_validate_missing_meta() -> None:
    errors = validate_template({"triggers": {"en": ["x"]}, "prompt": {"system_directive": "y", "output_schema": "z"}})
    assert any("meta" in e for e in errors)


def test_validate_missing_triggers() -> None:
    errors = validate_template({
        "meta": {"name": "t", "category": "ANALYTICAL", "version": "1", "author": "x"},
        "prompt": {"system_directive": "y", "output_schema": "z"},
    })
    assert any("triggers" in e for e in errors)


def test_validate_missing_prompt() -> None:
    errors = validate_template({
        "meta": {"name": "t", "category": "ANALYTICAL", "version": "1", "author": "x"},
        "triggers": {"en": ["x"]},
    })
    assert any("prompt" in e for e in errors)


def test_validate_invalid_category() -> None:
    data = {
        "meta": {"name": "t", "category": "INVALID", "version": "1", "author": "x"},
        "triggers": {"en": ["x"]},
        "prompt": {"system_directive": "y", "output_schema": "z"},
    }
    errors = validate_template(data)
    assert len(errors) > 0


def test_validate_invalid_strength() -> None:
    data = {
        "meta": {"name": "t", "category": "ANALYTICAL", "version": "1", "author": "x"},
        "triggers": {"en": ["x"], "strength": "ULTRA"},
        "prompt": {"system_directive": "y", "output_schema": "z"},
    }
    errors = validate_template(data)
    assert any("strength" in e for e in errors)


# ---------------------------------------------------------------------------
# load_template
# ---------------------------------------------------------------------------

def test_load_valid(valid_toml_file: Path) -> None:
    t = load_template(valid_toml_file)
    assert isinstance(t, Template)
    assert t.meta.name == "test-loader"
    assert t.meta.category.value == "ANALYTICAL"


def test_load_broken_toml(broken_toml_file: Path, capsys: pytest.CaptureFixture) -> None:
    t = load_template(broken_toml_file)
    assert t is None
    captured = capsys.readouterr()
    assert "TOML parse error" in captured.err


def test_load_missing_meta(missing_meta_toml: Path, capsys: pytest.CaptureFixture) -> None:
    t = load_template(missing_meta_toml)
    assert t is None
    captured = capsys.readouterr()
    assert "validation failed" in captured.err


def test_load_invalid_category(invalid_category_toml: Path, capsys: pytest.CaptureFixture) -> None:
    t = load_template(invalid_category_toml)
    assert t is None
    captured = capsys.readouterr()
    assert "validation failed" in captured.err


def test_load_invalid_strength(invalid_strength_toml: Path, capsys: pytest.CaptureFixture) -> None:
    t = load_template(invalid_strength_toml)
    assert t is None
    captured = capsys.readouterr()
    assert "validation failed" in captured.err


def test_load_nonexistent_file(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    t = load_template(tmp_path / "does_not_exist.toml")
    assert t is None
    captured = capsys.readouterr()
    assert "Cannot read template" in captured.err
