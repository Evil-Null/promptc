"""Trigger scoring functions for template matching.

Design reference: interceptor_plan_v2_final.md §A (line ~867).

Scoring formula (from §4.1):
    Score = W_trigger × TriggerScore + W_context × ContextScore + W_recency × RecencyScore

ContextScore and RecencyScore are stubbed as 0.0 in PR-3.
"""

from __future__ import annotations

from interceptor.config import RoutingConfig
from interceptor.models.template import Template
from interceptor.routing.index import PHRASE_BONUS, TriggerIndex, normalize_phrase, tokenize

# Strength multiplier (governs how strongly the template asserts its triggers)
_STRENGTH_MULTIPLIER: dict[str | None, float] = {
    "STRONG": 1.0,
    "MEDIUM": 0.75,
    "WEAK": 0.5,
    None: 0.75,  # Default when strength is unset
}


def score_triggers(
    input_text: str,
    template: Template,
    index: TriggerIndex,
) -> float:
    """Compute trigger score for *template* against *input_text*.

    Algorithm (per governing doc §A):
    1. Check multi-word phrase triggers first (1.5× bonus).
    2. Check single-token triggers.
    3. Best trigger wins (``max(scores)``).
    4. Apply strength multiplier from ``template.triggers.strength``.

    Returns 0.0 when no triggers match or input is empty.
    """
    if not input_text.strip():
        return 0.0

    tokens = tokenize(input_text)
    if not tokens:
        return 0.0

    template_triggers: set[str] = set()
    for phrase in template.triggers.en + template.triggers.ka:
        normalized = normalize_phrase(phrase)
        if normalized:
            template_triggers.add(normalized)

    scores: list[float] = []
    lowered = normalize_phrase(input_text)

    # --- Phase 1: phrase triggers (multi-word, higher priority) ---
    for trigger in template_triggers:
        if " " not in trigger:
            continue
        if trigger in lowered:
            for tpl_name, specificity in index.get(trigger, []):
                if tpl_name == template.meta.name:
                    scores.append(specificity * PHRASE_BONUS)

    # --- Phase 2: single-token triggers ---
    for token in tokens:
        if token not in index:
            continue
        for tpl_name, specificity in index[token]:
            if tpl_name == template.meta.name:
                scores.append(specificity)

    if not scores:
        return 0.0

    raw_score = max(scores)  # Best trigger wins (§A)
    multiplier = _STRENGTH_MULTIPLIER.get(template.triggers.strength, 0.75)
    return raw_score * multiplier


def score_template(
    input_text: str,
    template: Template,
    index: TriggerIndex,
    routing_config: RoutingConfig,
) -> float:
    """Compute weighted multi-signal score for *template*.

    Formula:
        Score = W_trigger × TriggerScore
              + W_context × ContextScore   (stubbed 0.0)
              + W_recency × RecencyScore   (stubbed 0.0)

    Uses weights from ``routing_config.weights``.
    """
    trigger_score = score_triggers(input_text, template, index)
    context_score = 0.0  # Stubbed — PR-4+
    recency_score = 0.0  # Stubbed — PR-4+

    w = routing_config.weights
    return (
        w.trigger * trigger_score
        + w.context * context_score
        + w.recency * recency_score
    )
