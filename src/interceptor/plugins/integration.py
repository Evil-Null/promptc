"""Thin integration layer wiring plugin hooks into compilation, routing, and backend."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Iterable

from interceptor.compilation.assembler import compile_prompt
from interceptor.constants import PLUGINS_DIR
from interceptor.plugins.discovery import discover_plugins
from interceptor.plugins.runtime import PluginRunner
from interceptor.routing.router import route as _route

if TYPE_CHECKING:
    from pathlib import Path

    import httpx

    from interceptor.adapters.models import ExecutionResult, StreamEvent
    from interceptor.adapters.service import AdapterService
    from interceptor.compilation.cache import CompiledTemplateCache
    from interceptor.compilation.models import CompiledPrompt, TokenBudget
    from interceptor.config import Config
    from interceptor.models.template import Template
    from interceptor.routing.models import RouteResult
    from interceptor.routing.router import ProjectContext
    from interceptor.template_registry import TemplateRegistry


def build_plugin_runner(plugins_dir: Path | None = None) -> PluginRunner:
    """Discover and load plugins into a fresh PluginRunner.

    Returns an empty runner if the directory is missing or has no valid plugins.
    """
    target = plugins_dir or PLUGINS_DIR
    if not target.is_dir():
        return PluginRunner([])

    try:
        discovered, warnings = discover_plugins(target)
    except Exception as exc:
        print(f"⚠️  Plugin discovery failed: {exc}", file=sys.stderr)
        return PluginRunner([])

    for w in warnings:
        print(f"⚠️  {w}", file=sys.stderr)

    return PluginRunner.from_discovered(discovered)


def compile_with_plugins(
    *,
    template: Template,
    raw_input: str,
    max_tokens: int = 8192,
    cache: CompiledTemplateCache | None = None,
    plugins_dir: Path | None = None,
) -> tuple[CompiledPrompt, TokenBudget]:
    """Compile a prompt with optional plugin precompile/postcompile hooks.

    Equivalent to compile_prompt() when no plugins are present.
    """
    runner = build_plugin_runner(plugins_dir)

    modified_input = runner.run_hook("precompile", raw_input)

    compiled, budget = compile_prompt(
        template=template,
        raw_input=modified_input,
        max_tokens=max_tokens,
        cache=cache,
    )

    compiled.compiled_text = runner.run_hook("postcompile", compiled.compiled_text)

    return compiled, budget


def route_with_plugins(
    text: str,
    registry: TemplateRegistry,
    config: Config,
    *,
    context: ProjectContext | None = None,
    explicit_template: str | None = None,
    plugins_dir: Path | None = None,
) -> RouteResult:
    """Route with optional plugin preroute/postroute hooks.

    Equivalent to route() when no plugins are present.
    """
    runner = build_plugin_runner(plugins_dir)

    modified_text = runner.run_hook("preroute", text)

    result = _route(
        modified_text,
        registry,
        config,
        context=context,
        explicit_template=explicit_template,
    )

    result = runner.run_hook("postroute", result)

    return result


def execute_with_plugins(
    *,
    service: AdapterService,
    backend: str,
    compiled_prompt: str | CompiledPrompt,
    temperature: float,
    max_output_tokens: int,
    client: httpx.Client | None = None,
    plugins_dir: Path | None = None,
) -> ExecutionResult:
    """Execute non-streaming backend request with presend/postreceive hooks.

    Equivalent to service.execute_full() when no plugins are present.
    """
    runner = build_plugin_runner(plugins_dir)

    modified_prompt = runner.run_hook("presend", compiled_prompt)

    result = service.execute_full(
        backend=backend,
        compiled_prompt=modified_prompt,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        client=client,
        plugin_runner=runner,
    )

    result = runner.run_hook("postreceive", result)

    return result


def execute_stream_with_plugins(
    *,
    service: AdapterService,
    backend: str,
    compiled_prompt: str | CompiledPrompt,
    temperature: float,
    max_output_tokens: int,
    client: httpx.Client | None = None,
    plugins_dir: Path | None = None,
) -> Iterable[StreamEvent]:
    """Execute streaming backend request with presend hook.

    Equivalent to service.execute_stream() when no plugins are present.
    Presend modifies the compiled prompt before dispatch. Postreceive does
    not apply to streaming (events are yielded progressively).
    """
    runner = build_plugin_runner(plugins_dir)

    modified_prompt = runner.run_hook("presend", compiled_prompt)

    return service.execute_stream(
        backend=backend,
        compiled_prompt=modified_prompt,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        client=client,
    )
