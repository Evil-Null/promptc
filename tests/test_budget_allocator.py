"""Tests for token budget allocator."""

from __future__ import annotations

import pytest

from interceptor.compilation.budget import (
    DEFAULT_MIN_RESERVE_TOKENS,
    DEFAULT_RESERVE_RATIO,
    allocate_token_budget,
)
from interceptor.compilation.models import CompressionLevel, TokenBudget


def _counts(
    none: int = 500,
    minify: int = 450,
    compact: int = 350,
    aggressive: int = 200,
    skeleton: int = 80,
) -> dict[CompressionLevel, int]:
    """Helper: build template token counts per level."""
    return {
        CompressionLevel.NONE: none,
        CompressionLevel.MINIFY: minify,
        CompressionLevel.COMPACT: compact,
        CompressionLevel.AGGRESSIVE: aggressive,
        CompressionLevel.SKELETON: skeleton,
    }


class TestAllocateTokenBudget:
    def test_selects_none_when_plenty_of_room(self) -> None:
        budget = allocate_token_budget(
            raw_input="hello",
            max_tokens=8192,
            template_token_counts=_counts(),
        )
        assert budget.compression_level == CompressionLevel.NONE
        assert budget.fits is True

    def test_selects_minify_when_none_too_large(self) -> None:
        budget = allocate_token_budget(
            raw_input="hello",
            max_tokens=700,
            template_token_counts=_counts(none=600, minify=400),
        )
        assert budget.compression_level == CompressionLevel.MINIFY
        assert budget.fits is True

    def test_selects_compact_when_needed(self) -> None:
        budget = allocate_token_budget(
            raw_input="hello",
            max_tokens=600,
            template_token_counts=_counts(none=600, minify=500, compact=300),
        )
        assert budget.compression_level == CompressionLevel.COMPACT
        assert budget.fits is True

    def test_selects_aggressive_when_needed(self) -> None:
        budget = allocate_token_budget(
            raw_input="hello",
            max_tokens=450,
            template_token_counts=_counts(
                none=600, minify=500, compact=400, aggressive=180
            ),
        )
        assert budget.compression_level == CompressionLevel.AGGRESSIVE
        assert budget.fits is True

    def test_selects_skeleton_when_needed(self) -> None:
        budget = allocate_token_budget(
            raw_input="hello",
            max_tokens=350,
            template_token_counts=_counts(
                none=600, minify=500, compact=400, aggressive=300, skeleton=60
            ),
        )
        assert budget.compression_level == CompressionLevel.SKELETON
        assert budget.fits is True

    def test_fits_false_when_skeleton_exceeds(self) -> None:
        budget = allocate_token_budget(
            raw_input="hello",
            max_tokens=100,
            template_token_counts=_counts(
                none=600, minify=500, compact=400, aggressive=300, skeleton=200
            ),
        )
        assert budget.compression_level == CompressionLevel.SKELETON
        assert budget.fits is False

    def test_huge_raw_input_fits_false(self) -> None:
        big_input = " ".join(["word"] * 5000)
        budget = allocate_token_budget(
            raw_input=big_input,
            max_tokens=1000,
            template_token_counts=_counts(),
        )
        assert budget.fits is False
        assert budget.available_system_tokens == 0

    def test_reserve_uses_min_reserve(self) -> None:
        budget = allocate_token_budget(
            raw_input="hi",
            max_tokens=500,
            template_token_counts=_counts(skeleton=10),
        )
        # 500 * 0.15 = 75, but min is 200
        assert budget.reserve_tokens == DEFAULT_MIN_RESERVE_TOKENS

    def test_reserve_uses_ratio_when_larger(self) -> None:
        budget = allocate_token_budget(
            raw_input="hi",
            max_tokens=10000,
            template_token_counts=_counts(),
        )
        expected_reserve = int(10000 * DEFAULT_RESERVE_RATIO)
        assert budget.reserve_tokens == expected_reserve
        assert budget.reserve_tokens > DEFAULT_MIN_RESERVE_TOKENS

    def test_no_negative_available_system_tokens(self) -> None:
        budget = allocate_token_budget(
            raw_input=" ".join(["word"] * 3000),
            max_tokens=100,
            template_token_counts=_counts(),
        )
        assert budget.available_system_tokens >= 0

    def test_custom_reserve_params(self) -> None:
        budget = allocate_token_budget(
            raw_input="hi",
            max_tokens=1000,
            template_token_counts=_counts(skeleton=10),
            reserve_ratio=0.25,
            min_reserve_tokens=100,
        )
        assert budget.reserve_tokens == max(100, int(1000 * 0.25))

    def test_returns_token_budget_type(self) -> None:
        budget = allocate_token_budget(
            raw_input="hi",
            max_tokens=8192,
            template_token_counts=_counts(),
        )
        assert isinstance(budget, TokenBudget)

    def test_user_tokens_positive(self) -> None:
        budget = allocate_token_budget(
            raw_input="review this code",
            max_tokens=8192,
            template_token_counts=_counts(),
        )
        assert budget.user_tokens > 0
