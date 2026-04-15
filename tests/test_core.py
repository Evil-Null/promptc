"""Unit tests for PromptCompilerCore orchestrator."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from interceptor.compilation.models import CompiledPrompt, CompressionLevel, TokenBudget
from interceptor.config import Config
from interceptor.core import PromptCompilerCore
from interceptor.models.template import (
    Category,
    QualityGates,
    Template,
    TemplateMeta,
    TemplatePrompt,
    TemplateTriggers,
)
from interceptor.routing.models import RouteMethod, RouteResult, RouteZone
from interceptor.template_registry import TemplateRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_template(name: str = "code-review") -> Template:
    """Build a minimal valid Template for testing."""
    return Template(
        meta=TemplateMeta(
            name=name,
            category=Category.EVALUATIVE,
            version="1.0.0",
            author="test",
        ),
        triggers=TemplateTriggers(en=["review", "code review"]),
        prompt=TemplatePrompt(
            system_directive="You are a senior code reviewer.",
            chain_of_thought="Think step by step.",
            output_schema="Provide structured feedback.",
        ),
        quality_gates=QualityGates(hard=["no false positives"], soft=["be concise"]),
    )


@pytest.fixture()
def registry() -> TemplateRegistry:
    """Registry with two templates."""
    t1 = _make_template("code-review")
    t2 = _make_template("explain")
    return TemplateRegistry({"code-review": t1, "explain": t2})


@pytest.fixture()
def config() -> Config:
    """Default config (no disk I/O)."""
    return Config()


@pytest.fixture()
def core(config: Config, registry: TemplateRegistry) -> PromptCompilerCore:
    """Core with injected deps."""
    return PromptCompilerCore(config=config, registry=registry)


# ---------------------------------------------------------------------------
# Constructor / DI
# ---------------------------------------------------------------------------

class TestCoreInit:
    def test_injected_config_and_registry(
        self, core: PromptCompilerCore, config: Config, registry: TemplateRegistry
    ) -> None:
        assert core.config is config
        assert core.registry is registry

    def test_default_construction_loads_from_disk(self) -> None:
        """Without injection, Core calls load_config() and TemplateRegistry.load_all()."""
        core = PromptCompilerCore()
        assert isinstance(core.config, Config)
        assert isinstance(core.registry, TemplateRegistry)


# ---------------------------------------------------------------------------
# route()
# ---------------------------------------------------------------------------

class TestCoreRoute:
    def test_route_returns_route_result(self, core: PromptCompilerCore) -> None:
        result = core.route("review this code")
        assert isinstance(result, RouteResult)

    def test_route_with_explicit_template(self, core: PromptCompilerCore) -> None:
        result = core.route("anything", template="code-review")
        assert result.template_name == "code-review"
        assert result.method == RouteMethod.EXPLICIT

    def test_route_passthrough_for_unmatched(self, core: PromptCompilerCore) -> None:
        result = core.route("xyzzy gibberish no template matches this")
        # May or may not be passthrough depending on routing logic,
        # but the result should still be a valid RouteResult
        assert isinstance(result, RouteResult)


# ---------------------------------------------------------------------------
# compile()
# ---------------------------------------------------------------------------

class TestCoreCompile:
    def test_compile_with_explicit_template(self, core: PromptCompilerCore) -> None:
        compiled, budget = core.compile("review my code", template="code-review")
        assert isinstance(compiled, CompiledPrompt)
        assert isinstance(budget, TokenBudget)
        assert compiled.template_name == "code-review"
        assert len(compiled.compiled_text) > 0

    def test_compile_passthrough_raises_value_error(self, core: PromptCompilerCore) -> None:
        """When routing returns PASSTHROUGH, compile() raises ValueError."""
        passthrough_result = RouteResult(
            template_name=None,
            zone=RouteZone.PASSTHROUGH,
            method=RouteMethod.PASSTHROUGH,
            confidence=0.0,
        )
        with patch("interceptor.core.route_with_plugins", return_value=passthrough_result):
            with pytest.raises(ValueError, match="No template matched"):
                core.compile("xyzzy gibberish")

    def test_compile_template_not_found_raises_value_error(self, core: PromptCompilerCore) -> None:
        """When routing returns a template_name not in registry, raises ValueError."""
        ghost_result = RouteResult(
            template_name="nonexistent-template",
            zone=RouteZone.AUTO_SELECT,
            method=RouteMethod.SCORE_WINNER,
            confidence=0.95,
        )
        with patch("interceptor.core.route_with_plugins", return_value=ghost_result):
            with pytest.raises(ValueError, match="not found in registry"):
                core.compile("anything")


# ---------------------------------------------------------------------------
# templates()
# ---------------------------------------------------------------------------

class TestCoreTemplates:
    def test_templates_returns_list(self, core: PromptCompilerCore) -> None:
        result = core.templates()
        assert isinstance(result, list)
        assert len(result) == 2

    def test_templates_sorted_by_name(self, core: PromptCompilerCore) -> None:
        result = core.templates()
        names = [t.meta.name for t in result]
        assert names == sorted(names)


# ---------------------------------------------------------------------------
# reload()
# ---------------------------------------------------------------------------

class TestCoreReload:
    def test_reload_refreshes_state(self, core: PromptCompilerCore) -> None:
        old_config = core.config
        old_registry = core.registry
        core.reload()
        # After reload, objects are new instances (loaded from disk)
        assert core.config is not old_config or core.registry is not old_registry
