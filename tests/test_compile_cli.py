"""Tests for compile CLI command and health check integration."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from interceptor.cli import app
from interceptor.health import check_compilation_valid

runner = CliRunner()


class TestCompileCommand:
    def test_success_with_valid_template(self) -> None:
        result = runner.invoke(
            app, ["compile", "review auth.py", "--template", "code-review"]
        )
        assert result.exit_code == 0
        assert "Compiled Prompt" in result.output
        assert "Compilation Metadata" in result.output

    def test_json_output(self) -> None:
        result = runner.invoke(
            app,
            ["compile", "review auth.py", "--template", "code-review", "--json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["template_name"] == "code-review"
        assert "compiled_text" in data
        assert "compression_level" in data
        assert "token_count_estimate" in data
        assert "fits" in data

    def test_unknown_template_exits_nonzero(self) -> None:
        result = runner.invoke(
            app, ["compile", "hello", "--template", "nonexistent-template"]
        )
        assert result.exit_code != 0
        assert "unknown template" in result.output.lower()

    def test_custom_max_tokens(self) -> None:
        result = runner.invoke(
            app,
            [
                "compile",
                "review auth.py",
                "--template",
                "code-review",
                "--max-tokens",
                "4096",
                "--json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["fits"] is True or data["fits"] is False

    def test_very_small_max_tokens_reports_no_fit(self) -> None:
        result = runner.invoke(
            app,
            [
                "compile",
                "review auth.py",
                "--template",
                "code-review",
                "--max-tokens",
                "10",
                "--json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["fits"] is False

    def test_all_builtin_templates(self) -> None:
        for tpl_name in ["code-review", "explain", "architecture", "security-audit"]:
            result = runner.invoke(
                app, ["compile", "test input", "--template", tpl_name, "--json"]
            )
            assert result.exit_code == 0, f"Failed for {tpl_name}: {result.output}"

    def test_template_short_flag(self) -> None:
        result = runner.invoke(
            app, ["compile", "review auth.py", "-t", "code-review", "--json"]
        )
        assert result.exit_code == 0

    def test_georgian_input_preserved(self) -> None:
        result = runner.invoke(
            app,
            [
                "compile",
                "შეამოწმე კოდი უსაფრთხოებისთვის",
                "--template",
                "code-review",
                "--json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "შეამოწმე" in data["compiled_text"]


class TestHealthCheckIntegration:
    def test_health_includes_compilation_valid(self) -> None:
        result = runner.invoke(app, ["health"])
        assert result.exit_code == 0
        assert "compilation_valid" in result.output

    def test_health_compilation_check_passes(self) -> None:
        result = runner.invoke(app, ["health"])
        assert result.exit_code == 0
        # The health output should show compilation_valid as passing.
        output_lower = result.output.lower()
        assert "compilation_valid" in output_lower

    def test_health_compilation_check_specific(self) -> None:
        result = runner.invoke(app, ["health", "--check", "compilation_valid"])
        assert result.exit_code == 0
        assert "compilation_valid" in result.output


class TestCheckCompilationValidDirect:
    """Direct unit tests for check_compilation_valid failure paths."""

    def test_passes_with_real_templates(self) -> None:
        result = check_compilation_valid()
        assert result.status == "pass"

    def test_fails_on_assembler_exception(self) -> None:
        with patch(
            "interceptor.compilation.assembler.assemble_compiled_prompt",
            side_effect=RuntimeError("boom"),
        ):
            result = check_compilation_valid()
            assert result.status == "fail"
            assert "boom" in result.message

    def test_fails_on_empty_compiled_text(self) -> None:
        from interceptor.compilation.models import CompiledPrompt, CompressionLevel

        fake = CompiledPrompt(
            template_name="t",
            raw_input="x",
            compiled_text="",
            token_count_estimate=0,
            compression_level=CompressionLevel.NONE,
        )
        with patch(
            "interceptor.compilation.assembler.assemble_compiled_prompt",
            return_value=fake,
        ):
            result = check_compilation_valid()
            assert result.status == "fail"
            assert "empty" in result.message

    def test_fails_on_missing_start_delimiter(self) -> None:
        from interceptor.compilation.models import CompiledPrompt, CompressionLevel

        fake = CompiledPrompt(
            template_name="t",
            raw_input="x",
            compiled_text="some text <<<USER_INPUT_END>>>",
            token_count_estimate=10,
            compression_level=CompressionLevel.NONE,
        )
        with patch(
            "interceptor.compilation.assembler.assemble_compiled_prompt",
            return_value=fake,
        ):
            result = check_compilation_valid()
            assert result.status == "fail"
            assert "start delimiter" in result.message

    def test_fails_on_missing_end_delimiter(self) -> None:
        from interceptor.compilation.models import CompiledPrompt, CompressionLevel

        fake = CompiledPrompt(
            template_name="t",
            raw_input="x",
            compiled_text="some text <<<USER_INPUT_START>>>",
            token_count_estimate=10,
            compression_level=CompressionLevel.NONE,
        )
        with patch(
            "interceptor.compilation.assembler.assemble_compiled_prompt",
            return_value=fake,
        ):
            result = check_compilation_valid()
            assert result.status == "fail"
            assert "end delimiter" in result.message

    def test_fails_on_zero_token_estimate(self) -> None:
        from interceptor.compilation.models import CompiledPrompt, CompressionLevel

        fake = CompiledPrompt(
            template_name="t",
            raw_input="x",
            compiled_text="<<<USER_INPUT_START>>> x <<<USER_INPUT_END>>>",
            token_count_estimate=0,
            compression_level=CompressionLevel.NONE,
        )
        with patch(
            "interceptor.compilation.assembler.assemble_compiled_prompt",
            return_value=fake,
        ):
            result = check_compilation_valid()
            assert result.status == "fail"
            assert "token estimate" in result.message
