"""Compilation pipeline data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Optional


class PipelineState(StrEnum):
    """Pipeline execution state."""

    RECEIVED = "received"
    ANALYZED = "analyzed"
    ROUTED = "routed"
    COMPILED = "compiled"


class CompressionLevel(StrEnum):
    """Template compression intensity (0–4)."""

    NONE = "none"
    MINIFY = "minify"
    COMPACT = "compact"
    AGGRESSIVE = "aggressive"
    SKELETON = "skeleton"


# Ordered from least to most destructive for budget selection.
COMPRESSION_ORDER: list[CompressionLevel] = [
    CompressionLevel.NONE,
    CompressionLevel.MINIFY,
    CompressionLevel.COMPACT,
    CompressionLevel.AGGRESSIVE,
    CompressionLevel.SKELETON,
]


@dataclass(slots=True)
class TokenBudget:
    """Result of token budget allocation."""

    max_tokens: int
    reserve_tokens: int
    user_tokens: int
    available_system_tokens: int
    fits: bool
    compression_level: CompressionLevel


@dataclass(slots=True)
class CompiledPrompt:
    """Assembled prompt ready for backend dispatch."""

    template_name: str
    raw_input: str
    compiled_text: str
    token_count_estimate: int
    compression_level: CompressionLevel
    sections_included: list[str] = field(default_factory=list)
    system_directive_text: str = ""
    chain_of_thought_text: str = ""
    output_schema_text: str = ""
    quality_gates_text: str = ""
    anti_patterns_text: str = ""
    user_input_text: str = ""


@dataclass(slots=True)
class PromptContext:
    """Minimal compilation-stage pipeline state."""

    state: PipelineState
    raw_input: str
    language: str = "unknown"
    route_result: Optional[object] = None
    compiled_prompt: Optional[CompiledPrompt] = None
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
