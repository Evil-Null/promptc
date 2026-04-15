"""Stateful orchestrator over the functional prompt-compilation pipeline.

PromptCompilerCore loads configuration and templates once, then serves
multiple compile / route requests without per-call filesystem overhead.
Designed as the engine behind the MCP server and any future integration.
"""

from __future__ import annotations

from interceptor.compilation.models import CompiledPrompt, TokenBudget
from interceptor.config import Config, load_config
from interceptor.models.template import Template
from interceptor.plugins.integration import compile_with_plugins, route_with_plugins
from interceptor.routing.models import RouteResult, RouteZone
from interceptor.template_registry import TemplateRegistry


class PromptCompilerCore:
    """Stateful orchestrator: config + registry loaded once, shared across calls.

    Supports dependency injection (config, registry) for testing without disk I/O.
    """

    __slots__ = ("_config", "_registry")

    def __init__(
        self,
        *,
        config: Config | None = None,
        registry: TemplateRegistry | None = None,
    ) -> None:
        self._config = config or load_config()
        self._registry = registry or TemplateRegistry.load_all()

    # -- public API -----------------------------------------------------------

    def route(self, text: str, *, template: str | None = None) -> RouteResult:
        """Route *text* to the best-matching template.

        If *template* is given it is passed as an explicit override.
        """
        return route_with_plugins(
            text,
            self._registry,
            self._config,
            explicit_template=template,
        )

    def compile(
        self,
        text: str,
        *,
        template: str | None = None,
        max_tokens: int = 8192,
    ) -> tuple[CompiledPrompt, TokenBudget]:
        """Route then compile *text*, returning the assembled prompt + budget.

        Raises ``ValueError`` if routing falls through to PASSTHROUGH
        (no template matched and none was explicitly requested).
        """
        result = self.route(text, template=template)

        if result.is_passthrough:
            raise ValueError(
                f"No template matched the input (zone={result.zone.value}). "
                "Pass an explicit template name or refine the query."
            )

        # Resolve template name → Template object
        tpl: Template | None = self._registry.get(result.template_name)  # type: ignore[arg-type]
        if tpl is None:
            raise ValueError(
                f"Template '{result.template_name}' was routed but not found in registry."
            )

        return compile_with_plugins(
            template=tpl,
            raw_input=text,
            max_tokens=max_tokens,
        )

    def templates(self) -> list[Template]:
        """Return all loaded templates, sorted by name."""
        return self._registry.list_all()

    def reload(self) -> None:
        """Re-read config and templates from disk (hot reload)."""
        self._config = load_config()
        self._registry = TemplateRegistry.load_all()

    # -- internal accessors (for testing / introspection) ---------------------

    @property
    def config(self) -> Config:
        """Current configuration snapshot."""
        return self._config

    @property
    def registry(self) -> TemplateRegistry:
        """Current template registry snapshot."""
        return self._registry
