"""Tests for template Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from interceptor.models.template import (
    Category,
    QualityGates,
    Template,
    TemplateMeta,
    TemplatePrompt,
    TemplateTriggers,
)


# ---------------------------------------------------------------------------
# Fixtures — minimal valid data
# ---------------------------------------------------------------------------

@pytest.fixture()
def valid_meta_data() -> dict:
    return {
        "name": "test-template",
        "category": "ANALYTICAL",
        "version": "1.0.0",
        "author": "test",
    }


@pytest.fixture()
def valid_triggers_data() -> dict:
    return {"en": ["test trigger"], "strength": "STRONG"}


@pytest.fixture()
def valid_prompt_data() -> dict:
    return {
        "system_directive": "You are a test assistant.",
        "output_schema": "Return structured output.",
    }


@pytest.fixture()
def valid_template_data(
    valid_meta_data: dict,
    valid_triggers_data: dict,
    valid_prompt_data: dict,
) -> dict:
    return {
        "meta": valid_meta_data,
        "triggers": valid_triggers_data,
        "prompt": valid_prompt_data,
    }


# ---------------------------------------------------------------------------
# Category enum
# ---------------------------------------------------------------------------

def test_category_values() -> None:
    assert set(Category) == {
        Category.ANALYTICAL,
        Category.CONSTRUCTIVE,
        Category.EVALUATIVE,
        Category.TRANSFORMATIVE,
        Category.COMMUNICATIVE,
    }


# ---------------------------------------------------------------------------
# TemplateMeta
# ---------------------------------------------------------------------------

def test_meta_valid(valid_meta_data: dict) -> None:
    meta = TemplateMeta(**valid_meta_data)
    assert meta.name == "test-template"
    assert meta.category == Category.ANALYTICAL
    assert meta.extends is None


def test_meta_empty_name_rejected() -> None:
    with pytest.raises(ValidationError, match="name must not be empty"):
        TemplateMeta(name="  ", category="ANALYTICAL", version="1", author="x")


def test_meta_invalid_category() -> None:
    with pytest.raises(ValidationError):
        TemplateMeta(name="t", category="INVALID", version="1", author="x")


def test_meta_extends_optional(valid_meta_data: dict) -> None:
    valid_meta_data["extends"] = "parent-template"
    meta = TemplateMeta(**valid_meta_data)
    assert meta.extends == "parent-template"


# ---------------------------------------------------------------------------
# TemplateTriggers
# ---------------------------------------------------------------------------

def test_triggers_en_only() -> None:
    t = TemplateTriggers(en=["hello"])
    assert t.en == ["hello"]
    assert t.ka == []


def test_triggers_ka_only() -> None:
    t = TemplateTriggers(ka=["გამარჯობა"])
    assert t.ka == ["გამარჯობა"]


def test_triggers_both_empty_rejected() -> None:
    with pytest.raises(ValidationError, match="At least one trigger"):
        TemplateTriggers()


def test_triggers_valid_strengths() -> None:
    for s in ("WEAK", "MEDIUM", "STRONG"):
        t = TemplateTriggers(en=["x"], strength=s)
        assert t.strength == s


def test_triggers_invalid_strength() -> None:
    with pytest.raises(ValidationError, match="strength must be one of"):
        TemplateTriggers(en=["x"], strength="ULTRA")


def test_triggers_none_strength_allowed() -> None:
    t = TemplateTriggers(en=["x"], strength=None)
    assert t.strength is None


# ---------------------------------------------------------------------------
# TemplatePrompt
# ---------------------------------------------------------------------------

def test_prompt_valid(valid_prompt_data: dict) -> None:
    p = TemplatePrompt(**valid_prompt_data)
    assert p.chain_of_thought == ""


def test_prompt_empty_directive_rejected() -> None:
    with pytest.raises(ValidationError, match="system_directive must not be empty"):
        TemplatePrompt(system_directive="  ", output_schema="ok")


def test_prompt_empty_schema_rejected() -> None:
    with pytest.raises(ValidationError, match="output_schema must not be empty"):
        TemplatePrompt(system_directive="ok", output_schema="  ")


# ---------------------------------------------------------------------------
# QualityGates
# ---------------------------------------------------------------------------

def test_quality_gates_defaults() -> None:
    q = QualityGates()
    assert q.hard == []
    assert q.soft == []


# ---------------------------------------------------------------------------
# Template (full model)
# ---------------------------------------------------------------------------

def test_template_valid(valid_template_data: dict) -> None:
    t = Template.model_validate(valid_template_data)
    assert t.meta.name == "test-template"
    assert t.quality_gates.hard == []
    assert t.anti_patterns == []
    assert t.parameters is None


def test_template_with_all_fields(valid_template_data: dict) -> None:
    valid_template_data["quality_gates"] = {
        "hard": ["must pass"],
        "soft": ["should pass"],
    }
    valid_template_data["anti_patterns"] = ["do not do this"]
    valid_template_data["parameters"] = {"language": "python"}
    t = Template.model_validate(valid_template_data)
    assert t.quality_gates.hard == ["must pass"]
    assert t.anti_patterns == ["do not do this"]
    assert t.parameters == {"language": "python"}


def test_template_extra_fields_ignored(valid_template_data: dict) -> None:
    valid_template_data["unknown_top_level"] = "should be ignored"
    valid_template_data["meta"]["future_field"] = "ignored"
    t = Template.model_validate(valid_template_data)
    assert t.meta.name == "test-template"


def test_template_missing_meta() -> None:
    with pytest.raises(ValidationError):
        Template.model_validate({"triggers": {"en": ["x"]}, "prompt": {"system_directive": "y", "output_schema": "z"}})


def test_template_missing_triggers() -> None:
    with pytest.raises(ValidationError):
        Template.model_validate({
            "meta": {"name": "t", "category": "ANALYTICAL", "version": "1", "author": "x"},
            "prompt": {"system_directive": "y", "output_schema": "z"},
        })
