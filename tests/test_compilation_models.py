"""Tests for compilation pipeline data models."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from interceptor.compilation.models import (
    COMPRESSION_ORDER,
    CompiledPrompt,
    CompressionLevel,
    PipelineState,
    PromptContext,
    TokenBudget,
)


class TestPipelineState:
    def test_values(self) -> None:
        assert PipelineState.RECEIVED == "received"
        assert PipelineState.ANALYZED == "analyzed"
        assert PipelineState.ROUTED == "routed"
        assert PipelineState.COMPILED == "compiled"

    def test_member_count(self) -> None:
        assert len(PipelineState) == 4


class TestCompressionLevel:
    def test_values(self) -> None:
        assert CompressionLevel.NONE == "none"
        assert CompressionLevel.MINIFY == "minify"
        assert CompressionLevel.COMPACT == "compact"
        assert CompressionLevel.AGGRESSIVE == "aggressive"
        assert CompressionLevel.SKELETON == "skeleton"

    def test_member_count(self) -> None:
        assert len(CompressionLevel) == 5

    def test_compression_order_matches(self) -> None:
        assert len(COMPRESSION_ORDER) == 5
        assert COMPRESSION_ORDER[0] == CompressionLevel.NONE
        assert COMPRESSION_ORDER[-1] == CompressionLevel.SKELETON


class TestTokenBudget:
    def test_construction(self) -> None:
        tb = TokenBudget(
            max_tokens=4096,
            reserve_tokens=200,
            user_tokens=50,
            available_system_tokens=3846,
            fits=True,
            compression_level=CompressionLevel.NONE,
        )
        assert tb.max_tokens == 4096
        assert tb.fits is True
        assert tb.compression_level == CompressionLevel.NONE

    def test_fits_false(self) -> None:
        tb = TokenBudget(
            max_tokens=100,
            reserve_tokens=200,
            user_tokens=50,
            available_system_tokens=0,
            fits=False,
            compression_level=CompressionLevel.SKELETON,
        )
        assert tb.fits is False


class TestCompiledPrompt:
    def test_construction(self) -> None:
        cp = CompiledPrompt(
            template_name="code-review",
            raw_input="review auth.py",
            compiled_text="SYSTEM DIRECTIVE:\n...\nUSER INPUT:\nreview auth.py",
            token_count_estimate=42,
            compression_level=CompressionLevel.NONE,
            sections_included=["system_directive"],
        )
        assert cp.template_name == "code-review"
        assert cp.token_count_estimate == 42
        assert "system_directive" in cp.sections_included

    def test_default_sections_list(self) -> None:
        cp = CompiledPrompt(
            template_name="t",
            raw_input="x",
            compiled_text="x",
            token_count_estimate=1,
            compression_level=CompressionLevel.NONE,
        )
        assert cp.sections_included == []


class TestPromptContext:
    def test_construction(self) -> None:
        ctx = PromptContext(state=PipelineState.RECEIVED, raw_input="hello")
        assert ctx.state == PipelineState.RECEIVED
        assert ctx.raw_input == "hello"
        assert ctx.language == "unknown"
        assert ctx.route_result is None
        assert ctx.compiled_prompt is None

    def test_created_at_utc(self) -> None:
        ctx = PromptContext(state=PipelineState.RECEIVED, raw_input="x")
        assert ctx.created_at.tzinfo is not None
        assert ctx.created_at.tzinfo == timezone.utc

    def test_state_transition(self) -> None:
        ctx = PromptContext(state=PipelineState.RECEIVED, raw_input="x")
        ctx.state = PipelineState.COMPILED
        assert ctx.state == PipelineState.COMPILED

    def test_compiled_prompt_assignment(self) -> None:
        ctx = PromptContext(state=PipelineState.RECEIVED, raw_input="x")
        cp = CompiledPrompt(
            template_name="t",
            raw_input="x",
            compiled_text="compiled",
            token_count_estimate=5,
            compression_level=CompressionLevel.MINIFY,
        )
        ctx.compiled_prompt = cp
        assert ctx.compiled_prompt is cp
