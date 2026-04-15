"""Fast local token estimation with optional tiktoken comparison."""

from __future__ import annotations

import re

# Heuristic: ~1.3 tokens per whitespace-separated word for English.
# Punctuation and special characters add extra tokens.
_WORD_TOKEN_RATIO = 1.3
_SPECIAL_CHAR_PATTERN = re.compile(r"[^\w\s]", re.UNICODE)


def estimate_tokens(text: str) -> int:
    """Return a deterministic token count estimate for *text*.

    Uses a word-count heuristic calibrated against GPT-style BPE tokenizers.
    Empty or whitespace-only input returns 0.
    """
    stripped = text.strip()
    if not stripped:
        return 0

    words = stripped.split()
    word_tokens = int(len(words) * _WORD_TOKEN_RATIO)

    special_count = len(_SPECIAL_CHAR_PATTERN.findall(stripped))
    return word_tokens + special_count


def compare_with_tiktoken_if_available(
    text: str,
) -> tuple[int, int | None]:
    """Return ``(local_estimate, tiktoken_count_or_none)``.

    If ``tiktoken`` is installed, encode with ``cl100k_base`` and return the
    actual count.  Otherwise the second element is ``None``.
    """
    local = estimate_tokens(text)
    try:
        import tiktoken  # type: ignore[import-untyped]

        enc = tiktoken.get_encoding("cl100k_base")
        actual = len(enc.encode(text))
        return local, actual
    except (ImportError, Exception):
        return local, None
