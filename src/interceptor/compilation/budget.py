"""Token budget allocator — 3-zone model (system + user + reserve)."""

from __future__ import annotations

from interceptor.compilation.models import (
    COMPRESSION_ORDER,
    CompressionLevel,
    TokenBudget,
)
from interceptor.compilation.tokenizer import estimate_tokens

DEFAULT_RESERVE_RATIO = 0.15
DEFAULT_MIN_RESERVE_TOKENS = 200


def allocate_token_budget(
    *,
    raw_input: str,
    max_tokens: int,
    template_token_counts: dict[CompressionLevel, int],
    reserve_ratio: float = DEFAULT_RESERVE_RATIO,
    min_reserve_tokens: int = DEFAULT_MIN_RESERVE_TOKENS,
) -> TokenBudget:
    """Select the least destructive compression level that fits the budget.

    3-zone model:
        total = system_zone (template) + user_zone (input) + reserve

    The reserve is ``max(min_reserve_tokens, floor(max_tokens * reserve_ratio))``.
    ``available_system_tokens = max_tokens - reserve - user_tokens``.
    The first compression level whose template token count fits within
    ``available_system_tokens`` is chosen.  If none fit, ``SKELETON`` is
    selected and ``fits`` is set to ``False`` when even SKELETON exceeds
    the budget.
    """
    user_tokens = estimate_tokens(raw_input)
    reserve = max(min_reserve_tokens, int(max_tokens * reserve_ratio))

    available_system = max_tokens - reserve - user_tokens
    if available_system < 0:
        available_system = 0

    chosen_level = CompressionLevel.SKELETON
    fits = False

    for level in COMPRESSION_ORDER:
        tpl_count = template_token_counts.get(level, 0)
        if tpl_count <= available_system:
            chosen_level = level
            fits = True
            break

    if not fits:
        skeleton_count = template_token_counts.get(CompressionLevel.SKELETON, 0)
        fits = skeleton_count <= available_system

    return TokenBudget(
        max_tokens=max_tokens,
        reserve_tokens=reserve,
        user_tokens=user_tokens,
        available_system_tokens=available_system,
        fits=fits,
        compression_level=chosen_level,
    )
