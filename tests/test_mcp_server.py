"""Unit tests for MCP server tool functions (direct async calls)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from interceptor.config import Config
from interceptor.core import PromptCompilerCore
from interceptor.mcp_server import (
    _get_core,
    promptc_optimize,
    promptc_reload,
    promptc_route,
    promptc_templates,
)
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


@pytest.fixture(autouse=True)
def _inject_core() -> None:
    """Replace the module-level _core with a test instance before every test."""
    import interceptor.mcp_server as mod

    t1 = _make_template("code-review")
    t2 = _make_template("explain")
    registry = TemplateRegistry({"code-review": t1, "explain": t2})
    config = Config()
    mod._core = PromptCompilerCore(config=config, registry=registry)
    yield
    mod._core = None


# ---------------------------------------------------------------------------
# promptc_optimize
# ---------------------------------------------------------------------------


class TestPromptcOptimize:
    @pytest.mark.anyio()
    async def test_optimize_returns_compiled_text(self) -> None:
        result = await promptc_optimize("review this code", template="code-review")
        assert isinstance(result, str)
        assert len(result) > 0
        assert "code reviewer" in result.lower() or "review" in result.lower()

    @pytest.mark.anyio()
    async def test_optimize_passthrough_returns_error_message(self) -> None:
        """When no template matches, returns [promptc] error instead of crashing."""
        passthrough = RouteResult(
            template_name=None,
            zone=RouteZone.PASSTHROUGH,
            method=RouteMethod.PASSTHROUGH,
            confidence=0.0,
        )
        with patch("interceptor.core.route_with_plugins", return_value=passthrough):
            result = await promptc_optimize("xyzzy random gibberish")
            assert result.startswith("[promptc]")
            assert "No template matched" in result


# ---------------------------------------------------------------------------
# promptc_route
# ---------------------------------------------------------------------------


class TestPromptcRoute:
    @pytest.mark.anyio()
    async def test_route_returns_valid_json(self) -> None:
        result = await promptc_route("review this code")
        data = json.loads(result)
        assert "template" in data
        assert "confidence" in data
        assert "zone" in data
        assert "method" in data
        assert isinstance(data["confidence"], float)

    @pytest.mark.anyio()
    async def test_route_explicit_template(self) -> None:
        """Route with text matching a known template should return it."""
        result = await promptc_route("review this code")
        data = json.loads(result)
        assert data["zone"] in ["PASSTHROUGH", "SUGGEST", "CONFIRM", "AUTO_SELECT"]


# ---------------------------------------------------------------------------
# promptc_templates
# ---------------------------------------------------------------------------


class TestPromptcTemplates:
    @pytest.mark.anyio()
    async def test_templates_returns_json_array(self) -> None:
        result = await promptc_templates()
        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) == 2

    @pytest.mark.anyio()
    async def test_templates_have_required_fields(self) -> None:
        result = await promptc_templates()
        data = json.loads(result)
        for item in data:
            assert "name" in item
            assert "category" in item
            assert "version" in item


# ---------------------------------------------------------------------------
# promptc_reload
# ---------------------------------------------------------------------------


class TestPromptcReload:
    @pytest.mark.anyio()
    async def test_reload_returns_success_message(self) -> None:
        result = await promptc_reload()
        assert "Reloaded" in result


# ---------------------------------------------------------------------------
# _get_core
# ---------------------------------------------------------------------------


class TestGetCore:
    def test_get_core_returns_singleton(self) -> None:
        core1 = _get_core()
        core2 = _get_core()
        assert core1 is core2

    def test_get_core_creates_instance(self) -> None:
        import interceptor.mcp_server as mod

        mod._core = None
        core = _get_core()
        assert isinstance(core, PromptCompilerCore)
