"""Phase-A probe tests — document current routing defects.

These tests use ``pytest.mark.xfail(strict=True)`` to assert that the current
behavior is broken. When the fixes land in Phase B/C, these tests should stop
failing; ``strict=True`` will then flip them to errors, forcing us to remove
the xfail markers. That is the intended migration path.

Scope:
    * Tokenizer must preserve token identity across punctuation variants.
    * Single generic nouns must not route to content-bearing templates.
    * Category-only matches must not cross into CONFIRM zone.
    * Unigram exact matches must not reach AUTO_SELECT.
"""

from __future__ import annotations

import pytest

from interceptor.core import PromptCompilerCore
from interceptor.routing.index import tokenize
from interceptor.routing.models import RouteZone


@pytest.fixture(scope="module")
def core() -> PromptCompilerCore:
    return PromptCompilerCore()


# ---------------------------------------------------------------------------
# Tokenizer normalization (Phase C will fix)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("clean", "punctuated"),
    [
        ("review", "review?"),
        ("security", "security!"),
        ("რევიუ", "რევიუ?"),
        ("ერორი", "ერორი!"),
    ],
)
def test_tokenizer_strips_terminal_punctuation(clean: str, punctuated: str) -> None:
    assert tokenize(clean) == tokenize(punctuated)


def test_georgian_punctuation_preserves_zone(core: PromptCompilerCore) -> None:
    clean = core.route("კოდის რევიუ")
    with_punct = core.route("კოდის რევიუ?")
    assert clean.zone == with_punct.zone, (
        f"Zone regressed: {clean.zone} → {with_punct.zone}"
    )


# ---------------------------------------------------------------------------
# Scoring defects (Phase B will fix)
# ---------------------------------------------------------------------------


def test_generic_noun_does_not_route(core: PromptCompilerCore) -> None:
    result = core.route("system")
    assert result.zone == RouteZone.PASSTHROUGH, (
        f"Single noun 'system' routed to {result.template_name} @ {result.confidence}"
    )


def test_noun_absorption_does_not_win(core: PromptCompilerCore) -> None:
    result = core.route("fix error in system")
    assert result.template_name != "architecture", (
        f"Noun 'system' absorbed — routed to architecture @ {result.confidence}"
    )


def test_category_only_match_caps_below_confirm(core: PromptCompilerCore) -> None:
    # "create" and "knowledge" hit CONSTRUCTIVE category keywords but do not
    # phrase-match any existing template. Should land in SUGGEST, not CONFIRM.
    result = core.route("create RAG knowledge base files")
    if result.template_name is not None:
        assert result.zone != RouteZone.CONFIRM, (
            f"Category-only match reached CONFIRM: {result.template_name} @ {result.confidence}"
        )


def test_unigram_match_caps_below_confirm(core: PromptCompilerCore) -> None:
    # "review" alone is a single-token exact match. Must cap at SUGGEST.
    result = core.route("review")
    assert result.zone in (RouteZone.SUGGEST, RouteZone.PASSTHROUGH), (
        f"Unigram 'review' reached {result.zone.value}: {result.template_name} @ {result.confidence}"
    )


# ---------------------------------------------------------------------------
# Coverage gaps (Phase E will fix)
# ---------------------------------------------------------------------------


def test_debugging_intent_has_a_home(core: PromptCompilerCore) -> None:
    result = core.route("debug this stack trace from production")
    assert result.template_name == "debugging"


def test_refactoring_intent_has_a_home(core: PromptCompilerCore) -> None:
    result = core.route("refactor this function to use DRY principles")
    assert result.template_name == "refactoring"


def test_task_planning_intent_has_a_home(core: PromptCompilerCore) -> None:
    result = core.route("create a todo list for this refactor")
    assert result.template_name == "task-planning"


def test_content_generation_intent_has_a_home(core: PromptCompilerCore) -> None:
    result = core.route("write documentation for this library")
    assert result.template_name == "content-generation"
