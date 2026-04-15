"""Pydantic v2 template models aligned with approved anatomy (Sections 3.1–3.3)."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class Category(str, Enum):
    """Template taxonomy — five intent categories."""

    ANALYTICAL = "ANALYTICAL"
    CONSTRUCTIVE = "CONSTRUCTIVE"
    EVALUATIVE = "EVALUATIVE"
    TRANSFORMATIVE = "TRANSFORMATIVE"
    COMMUNICATIVE = "COMMUNICATIVE"


class TemplateMeta(BaseModel):
    """Template identity and versioning."""

    model_config = ConfigDict(extra="ignore")

    name: str
    category: Category
    version: str
    author: str
    extends: str | None = None

    @field_validator("name")
    @classmethod
    def name_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Template name must not be empty")
        return v


_VALID_STRENGTHS = frozenset({"WEAK", "MEDIUM", "STRONG"})


class TemplateTriggers(BaseModel):
    """Trigger phrases for template matching."""

    model_config = ConfigDict(extra="ignore")

    en: list[str] = []
    ka: list[str] = []
    strength: str | None = None

    @field_validator("strength")
    @classmethod
    def validate_strength(cls, v: str | None) -> str | None:
        if v is not None and v not in _VALID_STRENGTHS:
            raise ValueError(
                f"strength must be one of {sorted(_VALID_STRENGTHS)}, got {v!r}"
            )
        return v

    @model_validator(mode="after")
    def at_least_one_trigger(self) -> TemplateTriggers:
        if not self.en and not self.ka:
            raise ValueError("At least one trigger in 'en' or 'ka' is required")
        return self


class TemplatePrompt(BaseModel):
    """Core prompt components."""

    model_config = ConfigDict(extra="ignore")

    system_directive: str
    chain_of_thought: str = ""
    output_schema: str

    @field_validator("system_directive")
    @classmethod
    def directive_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("system_directive must not be empty")
        return v

    @field_validator("output_schema")
    @classmethod
    def schema_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("output_schema must not be empty")
        return v


class QualityGates(BaseModel):
    """Hard and soft quality checks."""

    model_config = ConfigDict(extra="ignore")

    hard: list[str] = []
    soft: list[str] = []


class Template(BaseModel):
    """Complete template — the central model for prompt compilation."""

    model_config = ConfigDict(extra="ignore")

    meta: TemplateMeta
    triggers: TemplateTriggers
    prompt: TemplatePrompt
    quality_gates: QualityGates = QualityGates()
    anti_patterns: list[str] = []
    parameters: dict[str, str] | None = None
