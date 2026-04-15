"""Derive system and user text from a CompiledPrompt for adapter consumption."""

from __future__ import annotations

from interceptor.compilation.models import CompiledPrompt


def extract_system_text(compiled: CompiledPrompt) -> str:
    """Build system-side content from structured sections."""
    parts: list[str] = []
    if compiled.system_directive_text:
        parts.append(compiled.system_directive_text)
    if compiled.chain_of_thought_text:
        parts.append(compiled.chain_of_thought_text)
    if compiled.output_schema_text:
        parts.append(compiled.output_schema_text)
    if compiled.quality_gates_text:
        parts.append(compiled.quality_gates_text)
    if compiled.anti_patterns_text:
        parts.append(compiled.anti_patterns_text)
    return "\n\n".join(parts) if parts else compiled.compiled_text


def extract_user_text(compiled: CompiledPrompt) -> str:
    """Return the original user input for the user message slot."""
    return compiled.user_input_text or compiled.raw_input
