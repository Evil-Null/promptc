"""Tests for the specificity-weighted trigger index."""

from __future__ import annotations

import pytest

from interceptor.models.template import Template
from interceptor.routing.index import (
    PHRASE_BONUS,
    TriggerIndex,
    build_trigger_index,
    get_candidates,
    tokenize,
)
from interceptor.template_registry import TemplateRegistry


# ---------------------------------------------------------------------------
# Helpers — build minimal templates for testing
# ---------------------------------------------------------------------------

def _make_template(
    name: str,
    en: list[str] | None = None,
    ka: list[str] | None = None,
    strength: str | None = "STRONG",
) -> Template:
    return Template.model_validate({
        "meta": {
            "name": name,
            "category": "ANALYTICAL",
            "version": "1.0.0",
            "author": "test",
        },
        "triggers": {
            "en": en or ["default trigger"],
            "ka": ka or [],
            "strength": strength,
        },
        "prompt": {
            "system_directive": f"Directive for {name}.",
            "output_schema": "Return JSON.",
        },
    })


# ---------------------------------------------------------------------------
# tokenize
# ---------------------------------------------------------------------------

class TestTokenize:
    def test_basic_split(self) -> None:
        assert tokenize("Hello World") == ["hello", "world"]

    def test_lowercases(self) -> None:
        assert tokenize("REVIEW This Code") == ["review", "this", "code"]

    def test_strips_whitespace(self) -> None:
        assert tokenize("  review  code  ") == ["review", "code"]

    def test_empty_string(self) -> None:
        assert tokenize("") == []

    def test_whitespace_only(self) -> None:
        assert tokenize("   ") == []

    def test_georgian(self) -> None:
        assert tokenize("კოდის რევიუ") == ["კოდის", "რევიუ"]


# ---------------------------------------------------------------------------
# build_trigger_index
# ---------------------------------------------------------------------------

class TestBuildTriggerIndex:
    def test_empty_list(self) -> None:
        index = build_trigger_index([])
        assert index == {}

    def test_single_template(self) -> None:
        t = _make_template("alpha", en=["review code"])
        index = build_trigger_index([t])
        assert "review code" in index
        assert len(index["review code"]) == 1
        name, specificity = index["review code"][0]
        assert name == "alpha"
        assert specificity == 1.0

    def test_unique_triggers_have_specificity_one(self) -> None:
        t1 = _make_template("a", en=["unique trigger a"])
        t2 = _make_template("b", en=["unique trigger b"])
        index = build_trigger_index([t1, t2])
        for entries in index.values():
            assert len(entries) == 1
            assert entries[0][1] == 1.0

    def test_shared_trigger_halves_specificity(self) -> None:
        t1 = _make_template("a", en=["shared trigger"])
        t2 = _make_template("b", en=["shared trigger"])
        index = build_trigger_index([t1, t2])
        assert "shared trigger" in index
        entries = index["shared trigger"]
        assert len(entries) == 2
        for _name, specificity in entries:
            assert specificity == pytest.approx(0.5)

    def test_three_way_shared_specificity(self) -> None:
        templates = [
            _make_template("a", en=["common"]),
            _make_template("b", en=["common"]),
            _make_template("c", en=["common"]),
        ]
        index = build_trigger_index(templates)
        for _name, specificity in index["common"]:
            assert specificity == pytest.approx(1.0 / 3)

    def test_en_and_ka_combined(self) -> None:
        t = _make_template("mixed", en=["review"], ka=["რევიუ"])
        index = build_trigger_index([t])
        assert "review" in index
        assert "რევიუ" in index

    def test_deduplicates_within_template(self) -> None:
        t = _make_template("dup", en=["review", "Review", "REVIEW"])
        index = build_trigger_index([t])
        assert "review" in index
        entries = index["review"]
        assert len(entries) == 1
        assert entries[0][1] == 1.0

    def test_empty_trigger_strings_ignored(self) -> None:
        t = _make_template("e", en=["valid", ""])
        index = build_trigger_index([t])
        assert "valid" in index
        assert "" not in index

    def test_builtin_templates_index(self) -> None:
        reg = TemplateRegistry.load_all()
        index = build_trigger_index(reg.all_templates())
        assert len(index) > 0
        assert "code review" in index
        assert "კოდის რევიუ" in index


# ---------------------------------------------------------------------------
# get_candidates
# ---------------------------------------------------------------------------

class TestGetCandidates:
    def test_single_word_match(self) -> None:
        t = _make_template("alpha", en=["review"])
        index = build_trigger_index([t])
        tokens = tokenize("please review")
        assert get_candidates(index, tokens) == {"alpha"}

    def test_phrase_match(self) -> None:
        t = _make_template("beta", en=["code review"])
        index = build_trigger_index([t])
        tokens = tokenize("do a code review please")
        assert get_candidates(index, tokens) == {"beta"}

    def test_no_match_returns_empty(self) -> None:
        t = _make_template("gamma", en=["architecture"])
        index = build_trigger_index([t])
        tokens = tokenize("hello world")
        assert get_candidates(index, tokens) == set()

    def test_multiple_templates_matched(self) -> None:
        t1 = _make_template("a", en=["shared"])
        t2 = _make_template("b", en=["shared"])
        index = build_trigger_index([t1, t2])
        tokens = tokenize("shared topic")
        assert get_candidates(index, tokens) == {"a", "b"}

    def test_empty_tokens(self) -> None:
        t = _make_template("x", en=["anything"])
        index = build_trigger_index([t])
        assert get_candidates(index, []) == set()

    def test_georgian_match(self) -> None:
        t = _make_template("ka", ka=["კოდის რევიუ"])
        index = build_trigger_index([t])
        tokens = tokenize("კოდის რევიუ გააკეთე")
        assert get_candidates(index, tokens) == {"ka"}

    def test_builtin_candidates(self) -> None:
        reg = TemplateRegistry.load_all()
        index = build_trigger_index(reg.all_templates())
        tokens = tokenize("review this code")
        candidates = get_candidates(index, tokens)
        assert "code-review" in candidates
