"""Phase G — routing invariants that must hold after Phase B/C/E fixes.

These are the "bug can't come back" tests: structural properties of the
scorer that should remain true under any template set or corpus change.
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
# Tokenizer invariants
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("clean", "punctuated"),
    [
        ("review", "review?"),
        ("review", "review!"),
        ("review", "review."),
        ("review", "review,"),
        ("რევიუ", "რევიუ?"),
        ("ერორი", "ერორი!"),
    ],
)
def test_terminal_punctuation_never_changes_tokens(
    clean: str, punctuated: str
) -> None:
    assert tokenize(clean) == tokenize(punctuated)


def test_tokenizer_normalizes_nfc() -> None:
    # composed (NFC) and decomposed (NFD) sequences must yield identical tokens
    composed = "café review"
    decomposed = "cafe\u0301 review"
    assert tokenize(composed) == tokenize(decomposed)


# ---------------------------------------------------------------------------
# Scoring invariants
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "noun",
    ["system", "code", "project", "file", "thing"],
)
def test_single_generic_noun_does_not_reach_confirm(
    core: PromptCompilerCore, noun: str
) -> None:
    result = core.route(noun)
    assert result.zone in (RouteZone.PASSTHROUGH, RouteZone.SUGGEST), (
        f"Generic noun '{noun}' reached {result.zone}: "
        f"{result.template_name} @ {result.confidence}"
    )


@pytest.mark.parametrize(
    "verb",
    ["create", "design", "plan", "review", "analyze", "improve", "fix"],
)
def test_single_category_verb_caps_below_confirm(
    core: PromptCompilerCore, verb: str
) -> None:
    result = core.route(verb)
    assert result.zone in (RouteZone.PASSTHROUGH, RouteZone.SUGGEST), (
        f"Category verb '{verb}' reached {result.zone}: "
        f"{result.template_name} @ {result.confidence}"
    )


def test_punctuation_does_not_demote_zone(core: PromptCompilerCore) -> None:
    clean = core.route("კოდის რევიუ")
    with_punct = core.route("კოდის რევიუ?")
    assert clean.zone == with_punct.zone


# ---------------------------------------------------------------------------
# Coverage invariants — every intent has a home
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "template"),
    [
        ("debug this stack trace from production", "debugging"),
        ("refactor this function to use DRY principles", "refactoring"),
        ("create a todo list for this refactor", "task-planning"),
        ("write documentation for this library", "content-generation"),
        ("write unit tests for this module", "test-generation"),
        ("evaluate the quality of existing test suite", "test-review"),
        ("review this code", "code-review"),
        ("audit this code for security vulnerabilities", "security-audit"),
        ("design system architecture for a payment service", "architecture"),
        ("explain how this function works", "explain"),
    ],
)
def test_intent_routes_to_expected_template(
    core: PromptCompilerCore, text: str, template: str
) -> None:
    result = core.route(text)
    assert result.template_name == template, (
        f"{text!r} → {result.template_name} @ {result.confidence} "
        f"(expected {template})"
    )
