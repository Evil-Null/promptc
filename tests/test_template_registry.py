"""Tests for the template registry."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from interceptor.models.template import Template
from interceptor.template_registry import TemplateRegistry


# ---------------------------------------------------------------------------
# Helpers — write minimal valid TOML
# ---------------------------------------------------------------------------

def _write_template(directory: Path, name: str, category: str = "ANALYTICAL") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    toml_path = directory / f"{name}.toml"
    toml_path.write_text(
        f'[meta]\nname = "{name}"\ncategory = "{category}"\n'
        f'version = "1.0.0"\nauthor = "test"\n\n'
        f'[triggers]\nen = ["{name} trigger"]\n\n'
        f'[prompt]\nsystem_directive = "Test directive for {name}."\n'
        f'output_schema = "Return structured output."\n',
        encoding="utf-8",
    )
    return toml_path


def _write_invalid_template(directory: Path, name: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    toml_path = directory / f"{name}.toml"
    toml_path.write_text("[[broken\nnot valid", encoding="utf-8")
    return toml_path


# ---------------------------------------------------------------------------
# Tests — builtin only
# ---------------------------------------------------------------------------

def test_load_all_builtin_only(tmp_path: Path) -> None:
    builtin = tmp_path / "builtin"
    _write_template(builtin, "alpha")
    _write_template(builtin, "beta", "CONSTRUCTIVE")

    with (
        patch("interceptor.template_registry.TEMPLATES_BUILTIN_DIR", builtin),
        patch("interceptor.template_registry.TEMPLATES_CUSTOM_DIR", tmp_path / "custom"),
    ):
        reg = TemplateRegistry.load_all()

    assert reg.count() == 2
    assert reg.get("alpha") is not None
    assert reg.get("beta") is not None
    assert reg.get("nonexistent") is None


def test_list_all_sorted(tmp_path: Path) -> None:
    builtin = tmp_path / "builtin"
    _write_template(builtin, "zeta")
    _write_template(builtin, "alpha")

    with (
        patch("interceptor.template_registry.TEMPLATES_BUILTIN_DIR", builtin),
        patch("interceptor.template_registry.TEMPLATES_CUSTOM_DIR", tmp_path / "custom"),
    ):
        reg = TemplateRegistry.load_all()

    names = [t.meta.name for t in reg.list_all()]
    assert names == ["alpha", "zeta"]


# ---------------------------------------------------------------------------
# Tests — custom overrides builtin
# ---------------------------------------------------------------------------

def test_custom_overrides_builtin(tmp_path: Path) -> None:
    builtin = tmp_path / "builtin"
    custom = tmp_path / "custom"
    _write_template(builtin, "shared", "ANALYTICAL")
    _write_template(custom, "shared", "CONSTRUCTIVE")

    with (
        patch("interceptor.template_registry.TEMPLATES_BUILTIN_DIR", builtin),
        patch("interceptor.template_registry.TEMPLATES_CUSTOM_DIR", custom),
    ):
        reg = TemplateRegistry.load_all()

    assert reg.count() == 1
    t = reg.get("shared")
    assert t is not None
    assert t.meta.category.value == "CONSTRUCTIVE"


# ---------------------------------------------------------------------------
# Tests — invalid templates skipped
# ---------------------------------------------------------------------------

def test_invalid_templates_skipped(tmp_path: Path) -> None:
    builtin = tmp_path / "builtin"
    _write_template(builtin, "good")
    _write_invalid_template(builtin, "bad")

    with (
        patch("interceptor.template_registry.TEMPLATES_BUILTIN_DIR", builtin),
        patch("interceptor.template_registry.TEMPLATES_CUSTOM_DIR", tmp_path / "custom"),
    ):
        reg = TemplateRegistry.load_all()

    assert reg.count() == 1
    assert reg.get("good") is not None
    assert reg.get("bad") is None


# ---------------------------------------------------------------------------
# Tests — empty directories
# ---------------------------------------------------------------------------

def test_empty_directories(tmp_path: Path) -> None:
    builtin = tmp_path / "builtin"
    builtin.mkdir()
    custom = tmp_path / "custom"
    custom.mkdir()

    with (
        patch("interceptor.template_registry.TEMPLATES_BUILTIN_DIR", builtin),
        patch("interceptor.template_registry.TEMPLATES_CUSTOM_DIR", custom),
    ):
        reg = TemplateRegistry.load_all()

    assert reg.count() == 0
    assert reg.list_all() == []


def test_missing_directories(tmp_path: Path) -> None:
    with (
        patch("interceptor.template_registry.TEMPLATES_BUILTIN_DIR", tmp_path / "nope"),
        patch("interceptor.template_registry.TEMPLATES_CUSTOM_DIR", tmp_path / "also_nope"),
    ):
        reg = TemplateRegistry.load_all()

    assert reg.count() == 0


# ---------------------------------------------------------------------------
# Tests — real builtin templates load
# ---------------------------------------------------------------------------

def test_real_builtin_templates_load() -> None:
    reg = TemplateRegistry.load_all()
    assert reg.count() >= 3
    assert reg.get("code-review") is not None
    assert reg.get("architecture") is not None
    assert reg.get("explain") is not None
