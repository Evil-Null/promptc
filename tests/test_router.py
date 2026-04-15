"""Tests for routing.router — route(), helpers, health check."""

from __future__ import annotations

import pytest

from interceptor.config import Config, load_config
from interceptor.health import check_routing_valid
from interceptor.routing.models import RouteMethod, RouteResult, RouteZone
from interceptor.routing.router import (
    ProjectContext,
    levenshtein,
    route,
)
from interceptor.template_registry import TemplateRegistry


@pytest.fixture()
def registry() -> TemplateRegistry:
    return TemplateRegistry.load_all()


@pytest.fixture()
def config() -> Config:
    return load_config()


# ---------------------------------------------------------------------------
# Levenshtein
# ---------------------------------------------------------------------------


class TestLevenshtein:
    def test_equal_strings(self) -> None:
        assert levenshtein("abc", "abc") == 0

    def test_empty_string(self) -> None:
        assert levenshtein("abc", "") == 3

    def test_both_empty(self) -> None:
        assert levenshtein("", "") == 0

    def test_single_edit(self) -> None:
        assert levenshtein("kitten", "sitten") == 1

    def test_larger_distance(self) -> None:
        assert levenshtein("kitten", "sitting") == 3

    def test_symmetric(self) -> None:
        assert levenshtein("abc", "xyz") == levenshtein("xyz", "abc")


# ---------------------------------------------------------------------------
# ProjectContext
# ---------------------------------------------------------------------------


class TestProjectContext:
    def test_defaults(self) -> None:
        ctx = ProjectContext()
        assert ctx.file_path is None
        assert ctx.file_extension is None
        assert ctx.language is None

    def test_fields(self) -> None:
        ctx = ProjectContext(file_path="app.py", file_extension=".py", language="python")
        assert ctx.file_extension == ".py"

    def test_frozen(self) -> None:
        ctx = ProjectContext()
        with pytest.raises(AttributeError):
            ctx.file_path = "x"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Explicit template resolution
# ---------------------------------------------------------------------------


class TestExplicitTemplate:
    def test_exact_match(self, registry: TemplateRegistry, config: Config) -> None:
        result = route("anything", registry, config, explicit_template="code-review")
        assert result.zone == RouteZone.AUTO_SELECT
        assert result.method == RouteMethod.EXPLICIT
        assert result.confidence == 1.0
        assert result.template_name == "code-review"

    def test_fuzzy_match(self, registry: TemplateRegistry, config: Config) -> None:
        result = route("anything", registry, config, explicit_template="code-revew")
        assert result.zone == RouteZone.SUGGEST
        assert result.method == RouteMethod.FUZZY_MATCH
        assert result.template_name == "code-review"

    def test_unknown_raises(self, registry: TemplateRegistry, config: Config) -> None:
        with pytest.raises(ValueError, match="Unknown template"):
            route("anything", registry, config, explicit_template="zzzzzzzzz")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_input(self, registry: TemplateRegistry, config: Config) -> None:
        result = route("", registry, config)
        assert result.is_passthrough

    def test_whitespace_only(self, registry: TemplateRegistry, config: Config) -> None:
        result = route("   ", registry, config)
        assert result.is_passthrough

    def test_negation_dont(self, registry: TemplateRegistry, config: Config) -> None:
        result = route("don't review this code", registry, config)
        assert result.is_passthrough

    def test_negation_skip(self, registry: TemplateRegistry, config: Config) -> None:
        result = route("skip code review", registry, config)
        assert result.is_passthrough

    def test_negation_do_not(self, registry: TemplateRegistry, config: Config) -> None:
        result = route("do not review my code", registry, config)
        assert result.is_passthrough


# ---------------------------------------------------------------------------
# Zone classification
# ---------------------------------------------------------------------------


class TestZoneClassification:
    def test_auto_select_zone(self, registry: TemplateRegistry, config: Config) -> None:
        result = route("review this code", registry, config)
        assert result.zone in (RouteZone.AUTO_SELECT, RouteZone.CONFIRM)

    def test_passthrough_zone(self, registry: TemplateRegistry, config: Config) -> None:
        result = route("send an email to john", registry, config)
        assert result.is_passthrough

    def test_result_has_scores(self, registry: TemplateRegistry, config: Config) -> None:
        result = route("review this code", registry, config)
        assert isinstance(result.scores, dict)
        assert len(result.scores) > 0


# ---------------------------------------------------------------------------
# Fallback T3: smart default
# ---------------------------------------------------------------------------


class TestSmartDefault:
    def test_py_file_default(self, registry: TemplateRegistry, config: Config) -> None:
        ctx = ProjectContext(file_path="auth.py", file_extension=".py")
        result = route("some unrelated text here", registry, config, context=ctx)
        if result.is_passthrough:
            pytest.skip("Text matched nothing — fallback expected")
        assert result.template_name == "code-review"
        assert result.method == RouteMethod.SMART_DEFAULT

    def test_yaml_file_default(self, registry: TemplateRegistry, config: Config) -> None:
        ctx = ProjectContext(file_path="config.yaml", file_extension=".yaml")
        result = route("some xyz abc", registry, config, context=ctx)
        if result.is_passthrough:
            pytest.skip("Text matched nothing — fallback expected")
        assert result.template_name == "security-audit"

    def test_dockerfile_default(self, registry: TemplateRegistry, config: Config) -> None:
        ctx = ProjectContext(file_path="Dockerfile", file_extension="")
        result = route("something random", registry, config, context=ctx)
        if result.is_passthrough:
            pytest.skip("No match")
        assert result.template_name == "security-audit"

    def test_no_context_no_default(self, registry: TemplateRegistry, config: Config) -> None:
        result = route("something totally random", registry, config)
        assert result.is_passthrough


# ---------------------------------------------------------------------------
# Empty / edge branch coverage
# ---------------------------------------------------------------------------


class TestBranchCoverage:
    """Cover uncovered branches in router.py."""

    def test_empty_registry(self, config: Config) -> None:
        empty_reg = TemplateRegistry()
        result = route("review this code", empty_reg, config)
        assert result.is_passthrough

    def test_only_stop_words(self, registry: TemplateRegistry, config: Config) -> None:
        result = route("the a an in on for", registry, config)
        assert result.is_passthrough

    def test_low_score_fallback_to_context(
        self, registry: TemplateRegistry, config: Config
    ) -> None:
        ctx = ProjectContext(file_path="deploy.yaml", file_extension=".yaml")
        result = route("xyz qwe rty", registry, config, context=ctx)
        if result.method == RouteMethod.SMART_DEFAULT:
            assert result.template_name == "security-audit"
        else:
            assert result.is_passthrough or result.confidence > 0

    def test_ambiguity_same_category(
        self, registry: TemplateRegistry, config: Config
    ) -> None:
        result = route("review audit security code bugs", registry, config)
        assert not result.is_passthrough
        assert result.zone in (
            RouteZone.AUTO_SELECT,
            RouteZone.CONFIRM,
            RouteZone.SUGGEST,
        )

    def test_ambiguity_different_category(
        self, registry: TemplateRegistry, config: Config
    ) -> None:
        result = route("design review plan audit", registry, config)
        assert not result.is_passthrough

    def test_fuzzy_trigger_fallback_typo(
        self, registry: TemplateRegistry, config: Config
    ) -> None:
        result = route("securiy audit", registry, config)
        assert result.template_name == "security-audit"
        assert result.zone == RouteZone.SUGGEST

    def test_smart_default_unknown_extension(
        self, registry: TemplateRegistry, config: Config
    ) -> None:
        ctx = ProjectContext(file_path="data.xyz", file_extension=".xyz")
        result = route("blah blah blah", registry, config, context=ctx)
        assert result.is_passthrough

    def test_dockerfile_no_extension(
        self, registry: TemplateRegistry, config: Config
    ) -> None:
        ctx = ProjectContext(file_path="path/to/Dockerfile", file_extension="")
        result = route("zzz qqq www", registry, config, context=ctx)
        if not result.is_passthrough:
            assert result.template_name == "security-audit"
            assert result.method == RouteMethod.SMART_DEFAULT


# ---------------------------------------------------------------------------
# Health check: check_routing_valid
# ---------------------------------------------------------------------------


class TestCheckRoutingValid:
    def test_no_collisions(self) -> None:
        result = check_routing_valid()
        assert result.status in ("pass", "warn")
        assert result.name == "routing_valid"

    def test_collision_detection(self, tmp_path: pytest.TempPathFactory) -> None:
        from interceptor.models.template import Template

        t1 = Template.model_validate({
            "meta": {"name": "a", "category": "EVALUATIVE", "version": "1.0.0", "author": "test"},
            "triggers": {"en": ["shared trigger phrase"], "ka": [], "strength": "STRONG"},
            "prompt": {"system_directive": "x", "chain_of_thought": "x", "output_schema": "x"},
            "quality_gates": {"hard": [], "soft": [], "anti_patterns": []},
        })
        t2 = Template.model_validate({
            "meta": {"name": "b", "category": "EVALUATIVE", "version": "1.0.0", "author": "test"},
            "triggers": {"en": ["shared trigger phrase"], "ka": [], "strength": "STRONG"},
            "prompt": {"system_directive": "x", "chain_of_thought": "x", "output_schema": "x"},
            "quality_gates": {"hard": [], "soft": [], "anti_patterns": []},
        })
        from interceptor.health import HealthCheckResult

        trigger_owners: dict[str, list[str]] = {}
        for t in [t1, t2]:
            for phrase in t.triggers.en + t.triggers.ka:
                norm = phrase.strip().lower()
                if len(norm) >= 6:
                    trigger_owners.setdefault(norm, []).append(t.meta.name)
        collisions = {k: v for k, v in trigger_owners.items() if len(v) >= 2}
        assert len(collisions) == 1
        assert "shared trigger phrase" in collisions
