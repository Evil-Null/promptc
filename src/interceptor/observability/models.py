"""Observability value types — privacy-safe decision record."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(slots=True)
class DecisionRecord:
    """Single execution decision for JSONL logging.

    Privacy contract: no raw input, no raw response, no secrets.
    """

    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    decision_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    input_hash: str = ""
    selected_template: str = ""
    backend: str = ""
    finish_reason: str | None = None
    usage_input_tokens: int | None = None
    usage_output_tokens: int | None = None
    validation_status: str | None = None
    validation_score: float | None = None
    gate_score: float | None = None
    gate_hard_passed: bool | None = None
    retry_attempts: int | None = None
    retry_outcome: str | None = None
    outcome: str = "success"
    execution_time_ms: int | None = None
    error: str | None = None

    @staticmethod
    def hash_input(raw_input: str) -> str:
        """SHA-256 hex digest of *raw_input*."""
        return hashlib.sha256(raw_input.encode()).hexdigest()
