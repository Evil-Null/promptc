"""Specificity-weighted inverted index for template trigger matching.

Design reference: interceptor_plan_v2_final.md §A (line ~841).
"""

from __future__ import annotations

import unicodedata
from collections import Counter

from interceptor.models.template import Template

# ---------------------------------------------------------------------------
# Type alias — mirrors the governing doc's TRIGGER_INDEX signature
# Key:   lowercased trigger phrase
# Value: list of (template_name, specificity_weight) pairs
# ---------------------------------------------------------------------------
TriggerEntry = tuple[str, float]
TriggerIndex = dict[str, list[TriggerEntry]]

PHRASE_BONUS: float = 1.5  # Multi-word triggers get this multiplier (§A)

# Terminal punctuation stripped from tokens during normalization (Phase C).
# Covers ASCII, common Unicode, and Georgian-relevant marks. Internal
# punctuation (e.g. hyphen in "code-review") is preserved to avoid breaking
# compound tokens.
_TERMINAL_PUNCT: str = ".,;:!?—–-…·\u201c\u201d\u2018\u2019\"'()[]{}"


def _normalize_token(raw: str) -> str:
    """Normalize a single token: NFC, lowercase, strip terminal punctuation."""
    if not raw:
        return ""
    nfc = unicodedata.normalize("NFC", raw)
    return nfc.lower().strip(_TERMINAL_PUNCT)


def normalize_phrase(phrase: str) -> str:
    """Normalize a multi-word trigger phrase for indexing/matching."""
    tokens = [_normalize_token(t) for t in phrase.strip().split()]
    return " ".join(t for t in tokens if t)


# ---------------------------------------------------------------------------
# Index construction
# ---------------------------------------------------------------------------

def build_trigger_index(templates: list[Template]) -> TriggerIndex:
    """Build a specificity-weighted inverted index from *templates*.

    Pass 1: count how many templates each trigger phrase appears in.
    Pass 2: assign ``specificity = 1.0 / count`` for each entry.

    Each template's triggers are deduplicated (case-insensitive) before
    counting, so a trigger appearing twice in the same template counts once.
    """
    trigger_pairs: list[tuple[str, str]] = []

    for template in templates:
        seen: set[str] = set()
        for phrase in template.triggers.en + template.triggers.ka:
            normalized = normalize_phrase(phrase)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            trigger_pairs.append((normalized, template.meta.name))

    trigger_template_count: Counter[str] = Counter()
    for trigger, _name in trigger_pairs:
        trigger_template_count[trigger] += 1

    index: TriggerIndex = {}
    for trigger, template_name in trigger_pairs:
        specificity = 1.0 / trigger_template_count[trigger]
        index.setdefault(trigger, []).append((template_name, specificity))

    return index


# ---------------------------------------------------------------------------
# Tokenization
# ---------------------------------------------------------------------------

def tokenize(text: str) -> list[str]:
    """Normalize and split *text* into lowercase tokens.

    Normalization (Phase C):
        1. Unicode NFC normalization (combining chars → canonical).
        2. Lowercase.
        3. Strip terminal punctuation from each token.

    Internal punctuation (e.g. ``code-review``) is preserved.
    """
    return [
        tok for tok in (_normalize_token(t) for t in text.split())
        if tok
    ]


# ---------------------------------------------------------------------------
# Candidate retrieval
# ---------------------------------------------------------------------------

def get_candidates(
    index: TriggerIndex,
    tokens: list[str],
) -> set[str]:
    """Return template names that have at least one matching trigger.

    Generates all contiguous n-grams from *tokens* and checks each
    against the *index* keys, so both single-word and multi-word
    trigger phrases are matched.
    """
    candidates: set[str] = set()
    n = len(tokens)

    for length in range(n, 0, -1):
        for start in range(n - length + 1):
            phrase = " ".join(tokens[start : start + length])
            if phrase in index:
                for template_name, _specificity in index[phrase]:
                    candidates.add(template_name)

    return candidates
