"""Tests for token estimation."""

from __future__ import annotations

import pytest

from interceptor.compilation.tokenizer import (
    compare_with_tiktoken_if_available,
    estimate_tokens,
)


class TestEstimateTokens:
    def test_empty_string(self) -> None:
        assert estimate_tokens("") == 0

    def test_whitespace_only(self) -> None:
        assert estimate_tokens("   \n\t  ") == 0

    def test_single_word(self) -> None:
        result = estimate_tokens("hello")
        assert result >= 1

    def test_deterministic(self) -> None:
        text = "review this code for security bugs"
        a = estimate_tokens(text)
        b = estimate_tokens(text)
        assert a == b

    def test_longer_text_more_tokens(self) -> None:
        short = estimate_tokens("hello")
        long_ = estimate_tokens("hello world this is a longer sentence with more words")
        assert long_ > short

    def test_special_characters_add_tokens(self) -> None:
        plain = estimate_tokens("hello world")
        special = estimate_tokens("hello! world? foo; bar.")
        assert special > plain

    def test_mixed_english_georgian(self) -> None:
        result = estimate_tokens("review კოდი for vulnerabilities")
        assert result > 0

    def test_pure_georgian(self) -> None:
        result = estimate_tokens("შეამოწმე კოდი უსაფრთხოებისთვის")
        assert result > 0

    def test_multiline_text(self) -> None:
        text = "line one\nline two\nline three"
        result = estimate_tokens(text)
        assert result > 0

    def test_typical_prompt_range(self) -> None:
        # ~100 words should estimate roughly 100-200 tokens.
        text = " ".join(["word"] * 100)
        result = estimate_tokens(text)
        assert 100 <= result <= 200


class TestCompareWithTiktoken:
    def test_returns_tuple(self) -> None:
        result = compare_with_tiktoken_if_available("hello world")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_first_element_matches_estimate(self) -> None:
        text = "sample text for estimation"
        local = estimate_tokens(text)
        result_local, _ = compare_with_tiktoken_if_available(text)
        assert result_local == local

    def test_second_element_is_int_or_none(self) -> None:
        _, actual = compare_with_tiktoken_if_available("hello world")
        assert actual is None or isinstance(actual, int)

    def test_empty_string(self) -> None:
        local, _ = compare_with_tiktoken_if_available("")
        assert local == 0
