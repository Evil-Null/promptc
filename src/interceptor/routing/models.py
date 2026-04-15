"""Routing models — zones, methods, and route result."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RouteZone(str, Enum):
    """4-zone routing classification based on confidence score.

    Score: 0.0 ─── 0.30 ─── 0.55 ─── 0.80 ─── 1.0
    Zone:  PASSTHROUGH | SUGGEST  | CONFIRM  | AUTO_SELECT
    """

    PASSTHROUGH = "PASSTHROUGH"
    SUGGEST = "SUGGEST"
    CONFIRM = "CONFIRM"
    AUTO_SELECT = "AUTO_SELECT"


class RouteMethod(str, Enum):
    """How the routing decision was made."""

    SCORE_WINNER = "SCORE_WINNER"
    EXPLICIT = "EXPLICIT"
    FUZZY_MATCH = "FUZZY_MATCH"
    USER_CHOICE = "USER_CHOICE"
    CHAIN_SUGGESTED = "CHAIN_SUGGESTED"
    SMART_DEFAULT = "SMART_DEFAULT"
    CATEGORY_MATCH = "CATEGORY_MATCH"
    PASSTHROUGH = "PASSTHROUGH"


class RouteResult(BaseModel):
    """Immutable result of a routing decision."""

    model_config = ConfigDict(extra="ignore")

    template_name: str | None = None
    zone: RouteZone = RouteZone.PASSTHROUGH
    method: RouteMethod = RouteMethod.PASSTHROUGH
    confidence: float = 0.0
    runner_up: str | None = None
    scores: dict[str, float] = Field(default_factory=dict)

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        """Keep confidence in [0.0, 1.0]."""
        return max(0.0, min(1.0, v))

    @property
    def is_passthrough(self) -> bool:
        return self.zone == RouteZone.PASSTHROUGH

    @property
    def is_auto(self) -> bool:
        return self.zone == RouteZone.AUTO_SELECT
