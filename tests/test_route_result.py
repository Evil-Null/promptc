"""Tests for routing.models — RouteZone, RouteMethod, RouteResult."""

from __future__ import annotations

import json

import pytest

from interceptor.routing.models import RouteMethod, RouteResult, RouteZone


class TestRouteZone:
    def test_values(self) -> None:
        assert set(RouteZone) == {
            RouteZone.PASSTHROUGH,
            RouteZone.SUGGEST,
            RouteZone.CONFIRM,
            RouteZone.AUTO_SELECT,
        }

    def test_string_value(self) -> None:
        assert RouteZone.PASSTHROUGH.value == "PASSTHROUGH"
        assert RouteZone.AUTO_SELECT.value == "AUTO_SELECT"

    def test_is_str_enum(self) -> None:
        assert isinstance(RouteZone.PASSTHROUGH, str)


class TestRouteMethod:
    def test_values(self) -> None:
        assert len(RouteMethod) == 8

    def test_string_value(self) -> None:
        assert RouteMethod.SCORE_WINNER.value == "SCORE_WINNER"
        assert RouteMethod.FUZZY_MATCH.value == "FUZZY_MATCH"


class TestRouteResult:
    def test_defaults(self) -> None:
        r = RouteResult()
        assert r.template_name is None
        assert r.zone == RouteZone.PASSTHROUGH
        assert r.method == RouteMethod.PASSTHROUGH
        assert r.confidence == 0.0
        assert r.runner_up is None
        assert r.scores == {}

    def test_full_construction(self) -> None:
        r = RouteResult(
            template_name="code-review",
            zone=RouteZone.AUTO_SELECT,
            method=RouteMethod.SCORE_WINNER,
            confidence=0.92,
            runner_up="explain",
            scores={"code-review": 0.92, "explain": 0.40},
        )
        assert r.template_name == "code-review"
        assert r.confidence == 0.92

    def test_confidence_clamp_high(self) -> None:
        r = RouteResult(confidence=1.5)
        assert r.confidence == 1.0

    def test_confidence_clamp_low(self) -> None:
        r = RouteResult(confidence=-0.3)
        assert r.confidence == 0.0

    def test_confidence_zero(self) -> None:
        r = RouteResult(confidence=0.0)
        assert r.confidence == 0.0

    def test_confidence_one(self) -> None:
        r = RouteResult(confidence=1.0)
        assert r.confidence == 1.0

    def test_is_passthrough_true(self) -> None:
        r = RouteResult(zone=RouteZone.PASSTHROUGH)
        assert r.is_passthrough is True

    def test_is_passthrough_false(self) -> None:
        r = RouteResult(zone=RouteZone.CONFIRM)
        assert r.is_passthrough is False

    def test_is_auto_true(self) -> None:
        r = RouteResult(zone=RouteZone.AUTO_SELECT)
        assert r.is_auto is True

    def test_is_auto_false(self) -> None:
        r = RouteResult(zone=RouteZone.SUGGEST)
        assert r.is_auto is False

    def test_json_round_trip(self) -> None:
        r = RouteResult(
            template_name="explain",
            zone=RouteZone.CONFIRM,
            method=RouteMethod.CATEGORY_MATCH,
            confidence=0.65,
            scores={"explain": 0.65},
        )
        data = json.loads(r.model_dump_json())
        assert data["template_name"] == "explain"
        assert data["zone"] == "CONFIRM"
        assert data["confidence"] == 0.65

    def test_none_template_name(self) -> None:
        r = RouteResult(template_name=None)
        assert r.template_name is None

    def test_none_runner_up(self) -> None:
        r = RouteResult(runner_up=None)
        assert r.runner_up is None

    def test_scores_are_independent_instances(self) -> None:
        r1 = RouteResult()
        r2 = RouteResult()
        r1_scores = r1.scores
        r1_scores["x"] = 1.0
        assert "x" not in r2.scores

    def test_extra_fields_ignored(self) -> None:
        r = RouteResult(zone=RouteZone.SUGGEST, bogus_field="hello")
        assert not hasattr(r, "bogus_field")
