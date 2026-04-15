"""Tests for the `mycli templates` CLI command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from interceptor.cli import app

runner = CliRunner()


def test_templates_exits_zero() -> None:
    result = runner.invoke(app, ["templates"])
    assert result.exit_code == 0


def test_templates_lists_builtin_names() -> None:
    result = runner.invoke(app, ["templates"])
    assert "code-review" in result.output
    assert "architecture" in result.output
    assert "explain" in result.output


def test_templates_lists_categories() -> None:
    result = runner.invoke(app, ["templates"])
    assert "EVALUATIVE" in result.output
    assert "CONSTRUCTIVE" in result.output
    assert "COMMUNICATIVE" in result.output


def test_templates_lists_trigger_counts() -> None:
    result = runner.invoke(app, ["templates"])
    # code-review has 6 en + 3 ka = 9 triggers
    assert "9" in result.output


def test_templates_with_empty_dirs(tmp_path: Path) -> None:
    empty_builtin = tmp_path / "builtin"
    empty_builtin.mkdir()

    with (
        patch("interceptor.template_registry.TEMPLATES_BUILTIN_DIR", empty_builtin),
        patch("interceptor.template_registry.TEMPLATES_CUSTOM_DIR", tmp_path / "custom"),
    ):
        result = runner.invoke(app, ["templates"])

    assert result.exit_code == 0
    assert "No templates loaded" in result.output


def test_templates_with_custom_override(tmp_path: Path) -> None:
    builtin = tmp_path / "builtin"
    custom = tmp_path / "custom"
    builtin.mkdir()
    custom.mkdir()

    (builtin / "alpha.toml").write_text(
        '[meta]\nname = "alpha"\ncategory = "ANALYTICAL"\n'
        'version = "1.0.0"\nauthor = "test"\n\n'
        '[triggers]\nen = ["alpha trigger"]\n\n'
        '[prompt]\nsystem_directive = "Test."\noutput_schema = "Return JSON."\n',
        encoding="utf-8",
    )
    (custom / "alpha.toml").write_text(
        '[meta]\nname = "alpha"\ncategory = "CONSTRUCTIVE"\n'
        'version = "2.0.0"\nauthor = "user"\n\n'
        '[triggers]\nen = ["alpha custom trigger"]\n\n'
        '[prompt]\nsystem_directive = "Custom."\noutput_schema = "Return JSON."\n',
        encoding="utf-8",
    )

    with (
        patch("interceptor.template_registry.TEMPLATES_BUILTIN_DIR", builtin),
        patch("interceptor.template_registry.TEMPLATES_CUSTOM_DIR", custom),
    ):
        result = runner.invoke(app, ["templates"])

    assert result.exit_code == 0
    assert "CONSTRUCTIVE" in result.output
    assert "2.0.0" not in result.output or "alpha" in result.output


def test_health_templates_valid_pass() -> None:
    result = runner.invoke(app, ["health", "--check", "templates_valid"])
    assert result.exit_code == 0
    assert "pass" in result.output.lower() or "✅" in result.output


def test_health_templates_valid_fail(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    with (
        patch("interceptor.template_registry.TEMPLATES_BUILTIN_DIR", empty),
        patch("interceptor.template_registry.TEMPLATES_CUSTOM_DIR", tmp_path / "custom"),
    ):
        result = runner.invoke(app, ["health", "--check", "templates_valid"])

    assert result.exit_code == 1
    assert "fail" in result.output.lower() or "❌" in result.output
