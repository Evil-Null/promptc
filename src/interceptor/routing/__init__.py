"""Routing subsystem — trigger index, scoring, and 4-zone resolution."""

from interceptor.routing.index import (
    TriggerIndex,
    build_trigger_index,
    get_candidates,
    tokenize,
)
from interceptor.routing.models import RouteMethod, RouteResult, RouteZone
from interceptor.routing.router import ProjectContext, route
from interceptor.routing.scoring import score_template, score_triggers

__all__ = [
    "ProjectContext",
    "RouteMethod",
    "RouteResult",
    "RouteZone",
    "TriggerIndex",
    "build_trigger_index",
    "get_candidates",
    "route",
    "score_template",
    "score_triggers",
    "tokenize",
]
