"""Prompt assembler — combines template sections with user input."""

from __future__ import annotations

from typing import TYPE_CHECKING

from interceptor.compilation.cache import CompiledTemplateCache
from interceptor.compilation.compressor import (
    SECTION_KEYS,
    build_template_sections,
    compress_sections,
)
from interceptor.compilation.models import (
    COMPRESSION_ORDER,
    CompiledPrompt,
    CompressionLevel,
    TokenBudget,
)
from interceptor.compilation.tokenizer import estimate_tokens
from interceptor.compilation.budget import allocate_token_budget

if TYPE_CHECKING:
    from interceptor.models.template import Template

USER_INPUT_START = "<<<USER_INPUT_START>>>"
USER_INPUT_END = "<<<USER_INPUT_END>>>"

# Human-readable heading for each section key.
_SECTION_HEADINGS: dict[str, str] = {
    "system_directive": "SYSTEM DIRECTIVE",
    "chain_of_thought": "CHAIN OF THOUGHT",
    "output_schema": "OUTPUT SCHEMA",
    "quality_gates": "QUALITY GATES",
    "anti_patterns": "ANTI-PATTERNS",
}

# Default token budget when the caller does not specify.
_DEFAULT_MAX_TOKENS = 8192


def assemble_compiled_prompt(
    *,
    template: Template,
    raw_input: str,
    compression_level: CompressionLevel,
    compressed_sections: dict[str, str] | None = None,
) -> CompiledPrompt:
    """Build the final compiled prompt string from template + raw user input.

    If *compressed_sections* is provided (e.g. from cache), they are used
    directly.  Otherwise sections are built and compressed on the fly.
    """
    if compressed_sections is None:
        raw_sections = build_template_sections(template)
        compressed_sections, _ = compress_sections(raw_sections, compression_level)

    parts: list[str] = []
    sections_included: list[str] = []

    for key in SECTION_KEYS:
        if key in compressed_sections:
            heading = _SECTION_HEADINGS[key]
            parts.append(f"{heading}:\n{compressed_sections[key]}")
            sections_included.append(key)

    # User input block — always included.
    parts.append(
        f"USER INPUT:\n{USER_INPUT_START}\n{raw_input}\n{USER_INPUT_END}"
    )

    compiled_text = "\n\n".join(parts)
    token_count = estimate_tokens(compiled_text)

    return CompiledPrompt(
        template_name=template.meta.name,
        raw_input=raw_input,
        compiled_text=compiled_text,
        token_count_estimate=token_count,
        compression_level=compression_level,
        sections_included=sections_included,
    )


def compile_prompt(
    *,
    template: Template,
    raw_input: str,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
    cache: CompiledTemplateCache | None = None,
) -> tuple[CompiledPrompt, TokenBudget]:
    """End-to-end compilation: budget → compress → assemble.

    1. Build or fetch section variants for all compression levels.
    2. Estimate template token count per level.
    3. Allocate budget (selects least destructive fitting level).
    4. Assemble final compiled prompt at chosen level.
    5. Return (compiled_prompt, applied_budget).
    """
    # Step 1: get compressed sections per level.
    level_sections: dict[CompressionLevel, dict[str, str]] = {}

    for level in COMPRESSION_ORDER:
        cached = cache.get(template.meta.name, level) if cache else None
        if cached is not None:
            level_sections[level] = cached
        else:
            raw_sections = build_template_sections(template)
            compressed, _ = compress_sections(raw_sections, level)
            level_sections[level] = compressed

    # Step 2: estimate token counts per level.
    template_token_counts: dict[CompressionLevel, int] = {}
    for level in COMPRESSION_ORDER:
        sections = level_sections[level]
        combined = "\n\n".join(
            f"{_SECTION_HEADINGS[k]}:\n{sections[k]}"
            for k in SECTION_KEYS
            if k in sections
        )
        template_token_counts[level] = estimate_tokens(combined)

    # Step 3: allocate budget.
    budget = allocate_token_budget(
        raw_input=raw_input,
        max_tokens=max_tokens,
        template_token_counts=template_token_counts,
    )

    # Step 4: assemble at chosen level.
    chosen = budget.compression_level
    compiled = assemble_compiled_prompt(
        template=template,
        raw_input=raw_input,
        compression_level=chosen,
        compressed_sections=level_sections[chosen],
    )

    return compiled, budget
