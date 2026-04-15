"""Tests for PR-8 — compile→adapt boundary hardening."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from interceptor.adapters.claude import ClaudeAdapter
from interceptor.adapters.gpt import GptAdapter
from interceptor.adapters.prompt_extract import extract_system_text, extract_user_text
from interceptor.adapters.service import AdapterService
from interceptor.compilation.models import CompiledPrompt, CompressionLevel

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_compiled(
    *,
    system_directive: str = "You are a helpful assistant.",
    chain_of_thought: str = "Think step by step.",
    output_schema: str = "Return JSON.",
    quality_gates: str = "Hard: must compile",
    anti_patterns: str = "No eval()",
    user_input: str = "How do I sort a list?",
    compiled_text: str = "full compiled text here",
    template_name: str = "test-tpl",
) -> CompiledPrompt:
    return CompiledPrompt(
        template_name=template_name,
        raw_input=user_input,
        compiled_text=compiled_text,
        token_count_estimate=100,
        compression_level=CompressionLevel.NONE,
        sections_included=["system_directive", "chain_of_thought"],
        system_directive_text=system_directive,
        chain_of_thought_text=chain_of_thought,
        output_schema_text=output_schema,
        quality_gates_text=quality_gates,
        anti_patterns_text=anti_patterns,
        user_input_text=user_input,
    )


# ---------------------------------------------------------------------------
# A: CompiledPrompt structured fields
# ---------------------------------------------------------------------------


class TestCompiledPromptStructuredFields:
    """Verify new structured fields on CompiledPrompt."""

    def test_new_fields_have_defaults(self) -> None:
        cp = CompiledPrompt(
            template_name="t",
            raw_input="hello",
            compiled_text="full text",
            token_count_estimate=10,
            compression_level=CompressionLevel.NONE,
        )
        assert cp.system_directive_text == ""
        assert cp.chain_of_thought_text == ""
        assert cp.output_schema_text == ""
        assert cp.quality_gates_text == ""
        assert cp.anti_patterns_text == ""
        assert cp.user_input_text == ""

    def test_fields_populated(self) -> None:
        cp = _make_compiled()
        assert cp.system_directive_text == "You are a helpful assistant."
        assert cp.chain_of_thought_text == "Think step by step."
        assert cp.output_schema_text == "Return JSON."
        assert cp.quality_gates_text == "Hard: must compile"
        assert cp.anti_patterns_text == "No eval()"
        assert cp.user_input_text == "How do I sort a list?"


# ---------------------------------------------------------------------------
# B: prompt_extract helpers
# ---------------------------------------------------------------------------


class TestPromptExtract:
    """Test extract_system_text and extract_user_text."""

    def test_system_text_joins_sections(self) -> None:
        cp = _make_compiled()
        system = extract_system_text(cp)
        assert "You are a helpful assistant." in system
        assert "Think step by step." in system
        assert "Return JSON." in system
        assert "Hard: must compile" in system
        assert "No eval()" in system
        # User input should NOT be in system text.
        assert "How do I sort a list?" not in system

    def test_system_text_omits_empty_sections(self) -> None:
        cp = _make_compiled(chain_of_thought="", quality_gates="", anti_patterns="")
        system = extract_system_text(cp)
        assert "You are a helpful assistant." in system
        assert "Return JSON." in system
        # Only 2 non-empty sections → one separator.
        assert system.count("\n\n") == 1

    def test_system_text_falls_back_to_compiled_text(self) -> None:
        cp = CompiledPrompt(
            template_name="t",
            raw_input="hi",
            compiled_text="fallback text",
            token_count_estimate=5,
            compression_level=CompressionLevel.NONE,
        )
        assert extract_system_text(cp) == "fallback text"

    def test_user_text_returns_user_input(self) -> None:
        cp = _make_compiled()
        assert extract_user_text(cp) == "How do I sort a list?"

    def test_user_text_falls_back_to_raw_input(self) -> None:
        cp = CompiledPrompt(
            template_name="t",
            raw_input="raw input here",
            compiled_text="text",
            token_count_estimate=5,
            compression_level=CompressionLevel.NONE,
        )
        assert extract_user_text(cp) == "raw input here"


# ---------------------------------------------------------------------------
# C: Claude adapter system/user separation
# ---------------------------------------------------------------------------


class TestClaudeAdapterStructured:
    """Claude adapter properly separates system and user content."""

    def test_structured_prompt_separation(self) -> None:
        adapter = ClaudeAdapter()
        cp = _make_compiled()
        req = adapter.adapt(
            compiled_prompt=cp, temperature=0.7, max_output_tokens=4096, stream=False
        )
        system_content = req.payload["system"]
        user_content = req.payload["messages"][0]["content"]
        # System has instructional sections.
        assert "You are a helpful assistant." in system_content
        assert "Think step by step." in system_content
        # User message has actual user input.
        assert user_content == "How do I sort a list?"
        # No duplication — user input NOT in system.
        assert "How do I sort a list?" not in system_content

    def test_string_fallback_backward_compat(self) -> None:
        adapter = ClaudeAdapter()
        req = adapter.adapt(
            compiled_prompt="plain string prompt",
            temperature=0.5,
            max_output_tokens=2048,
            stream=False,
        )
        assert req.payload["system"] == "plain string prompt"
        assert req.payload["messages"][0]["content"] == "plain string prompt"

    def test_no_duplication_invariant(self) -> None:
        """The compiled_text must NOT appear in both system and user slots."""
        adapter = ClaudeAdapter()
        cp = _make_compiled()
        req = adapter.adapt(
            compiled_prompt=cp, temperature=0.7, max_output_tokens=4096, stream=False
        )
        system = req.payload["system"]
        user = req.payload["messages"][0]["content"]
        assert system != user, "System and user content must differ"


# ---------------------------------------------------------------------------
# D: GPT adapter system/user separation
# ---------------------------------------------------------------------------


class TestGptAdapterStructured:
    """GPT adapter properly separates system and user content."""

    def test_structured_prompt_separation(self) -> None:
        adapter = GptAdapter()
        cp = _make_compiled()
        req = adapter.adapt(
            compiled_prompt=cp, temperature=0.7, max_output_tokens=4096, stream=False
        )
        system_msg = req.payload["messages"][0]
        user_msg = req.payload["messages"][1]
        assert system_msg["role"] == "system"
        assert user_msg["role"] == "user"
        assert "You are a helpful assistant." in system_msg["content"]
        assert user_msg["content"] == "How do I sort a list?"
        assert "How do I sort a list?" not in system_msg["content"]

    def test_string_fallback_backward_compat(self) -> None:
        adapter = GptAdapter()
        req = adapter.adapt(
            compiled_prompt="plain string prompt",
            temperature=0.5,
            max_output_tokens=2048,
            stream=False,
        )
        msgs = req.payload["messages"]
        assert msgs[0]["content"] == "plain string prompt"
        assert msgs[1]["content"] == "plain string prompt"

    def test_no_duplication_invariant(self) -> None:
        adapter = GptAdapter()
        cp = _make_compiled()
        req = adapter.adapt(
            compiled_prompt=cp, temperature=0.7, max_output_tokens=4096, stream=False
        )
        system_content = req.payload["messages"][0]["content"]
        user_content = req.payload["messages"][1]["content"]
        assert system_content != user_content


# ---------------------------------------------------------------------------
# E: AdapterService with CompiledPrompt
# ---------------------------------------------------------------------------


class TestAdapterServiceStructured:
    """AdapterService accepts CompiledPrompt objects."""

    def test_service_adapt_with_compiled_prompt(self) -> None:
        service = AdapterService()
        cp = _make_compiled()
        req = service.adapt_request(
            backend="claude",
            compiled_prompt=cp,
            temperature=0.7,
            max_output_tokens=4096,
        )
        assert req.payload["system"] != req.payload["messages"][0]["content"]

    def test_service_adapt_with_string_still_works(self) -> None:
        service = AdapterService()
        req = service.adapt_request(
            backend="gpt",
            compiled_prompt="plain text",
            temperature=0.5,
            max_output_tokens=2048,
        )
        assert req.payload["messages"][0]["content"] == "plain text"


# ---------------------------------------------------------------------------
# F: Assembler fills structured fields
# ---------------------------------------------------------------------------


class TestAssemblerFillsStructuredFields:
    """assemble_compiled_prompt populates structured section fields."""

    def test_compile_prompt_fills_fields(self) -> None:
        from interceptor.compilation.assembler import compile_prompt
        from interceptor.template_registry import TemplateRegistry

        registry = TemplateRegistry.load_all()
        tpl = registry.get("code-review")
        assert tpl is not None, "code-review template must exist"

        cp, _budget = compile_prompt(template=tpl, raw_input="def foo(): pass")
        assert cp.user_input_text == "def foo(): pass"
        assert cp.system_directive_text != ""

    def test_user_input_text_matches_raw_input(self) -> None:
        from interceptor.compilation.assembler import compile_prompt
        from interceptor.template_registry import TemplateRegistry

        registry = TemplateRegistry.load_all()
        tpl = registry.get("code-review")
        assert tpl is not None
        text = "function hello() { return 42; }"
        cp, _budget = compile_prompt(template=tpl, raw_input=text)
        assert cp.user_input_text == text
        assert cp.raw_input == text


# ---------------------------------------------------------------------------
# G: CLI --dry-run integration
# ---------------------------------------------------------------------------


class TestRunCliDryRun:
    """mycli run --dry-run integration tests."""

    def test_dry_run_json_output(self) -> None:
        from interceptor.cli import app

        result = runner.invoke(
            app,
            ["run", "def foo(): pass", "--template", "code-review", "--backend", "claude", "--dry-run", "--json"],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["template"] == "code-review"
        assert data["backend"] == "claude"
        assert data["system_text_length"] > 0
        assert data["user_text_length"] > 0

    def test_dry_run_rich_output(self) -> None:
        from interceptor.cli import app

        result = runner.invoke(
            app,
            ["run", "def foo(): pass", "--template", "code-review", "--backend", "gpt", "--dry-run"],
        )
        assert result.exit_code == 0, result.output
        assert "System Content" in result.output
        assert "User Content" in result.output
        assert "Dry-run" in result.output

    def test_no_api_key_error_without_dry_run(self) -> None:
        """Without --dry-run, missing API key produces an error exit."""
        from interceptor.cli import app

        result = runner.invoke(
            app,
            ["run", "hello", "--template", "code-review", "--backend", "claude"],
        )
        assert result.exit_code == 1
        assert "api key" in result.output.lower() or "error" in result.output.lower()

    def test_unknown_template_error(self) -> None:
        from interceptor.cli import app

        result = runner.invoke(
            app,
            ["run", "hello", "--template", "nonexistent-template", "--backend", "claude", "--dry-run"],
        )
        assert result.exit_code == 1
        assert "Unknown template" in result.output

    def test_dry_run_no_duplication_in_payload(self) -> None:
        """System and user payloads should differ when using structured CompiledPrompt."""
        from interceptor.cli import app

        result = runner.invoke(
            app,
            ["run", "sort a list in python", "--template", "code-review", "--backend", "claude", "--dry-run", "--json"],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        system = data["payload"]["system"]
        user = data["payload"]["messages"][0]["content"]
        assert system != user, "System and user content must differ in structured mode"
