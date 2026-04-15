"""Routing subsystem — trigger index, scoring, and (future) resolution."""

from interceptor.routing.index import (
    TriggerIndex,
    build_trigger_index,
    get_candidates,
    tokenize,
)
from interceptor.routing.scoring import score_template, score_triggers

__all__ = [
    "TriggerIndex",
    "build_trigger_index",
    "get_candidates",
    "score_template",
    "score_triggers",
    "tokenize",
]
