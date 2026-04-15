"""CLI entry point — typer app with health and version commands."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from interceptor.constants import VERSION
from interceptor.health import (
    HealthCheckResult,
    check_backends_valid,
    check_compilation_valid,
    check_config_valid,
    check_routing_valid,
    check_templates_valid,
)

app = typer.Typer(
    name="mycli",
    help="Prompt Compiler — elite prompt engineering, automatically.",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()

# ---------------------------------------------------------------------------
# Available health checks (extensible in later phases)
# ---------------------------------------------------------------------------

_HEALTH_CHECKS: dict[str, Callable[..., HealthCheckResult]] = {
    "config_valid": check_config_valid,
    "templates_valid": check_templates_valid,
    "routing_valid": check_routing_valid,
    "compilation_valid": check_compilation_valid,
    "backends_valid": check_backends_valid,
}

_STATUS_STYLE: dict[str, str] = {
    "pass": "[green]✅ pass[/green]",
    "warn": "[yellow]⚠️  warn[/yellow]",
    "fail": "[red]❌ fail[/red]",
}


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@app.command()
def version() -> None:
    """Print the Prompt Compiler version."""
    console.print(VERSION)


@app.command()
def health(
    check: Annotated[
        Optional[str],
        typer.Option("--check", help="Run a specific health check by name."),
    ] = None,
    strict: Annotated[
        bool,
        typer.Option("--strict", help="Exit 1 on any warn or fail (CI mode)."),
    ] = False,
) -> None:
    """Run system health checks."""
    if check is not None:
        fn = _HEALTH_CHECKS.get(check)
        if fn is None:
            console.print(f"[red]Unknown check: {check}[/red]")
            raise typer.Exit(code=1)
        results = [fn()]
    else:
        results = [fn() for fn in _HEALTH_CHECKS.values()]

    _render_results(results)
    _exit_on_status(results, strict=strict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _render_results(results: list[HealthCheckResult]) -> None:
    """Render health check results as a Rich table."""
    table = Table(title="Health Checks", show_lines=True)
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Message")

    for r in results:
        table.add_row(r.name, _STATUS_STYLE.get(r.status, r.status), r.message)

    console.print(table)


def _exit_on_status(
    results: list[HealthCheckResult], *, strict: bool
) -> None:
    """Exit with appropriate code based on results and strict flag."""
    has_fail = any(r.status == "fail" for r in results)
    has_warn = any(r.status == "warn" for r in results)

    if has_fail:
        raise typer.Exit(code=1)
    if strict and has_warn:
        raise typer.Exit(code=1)


@app.command()
def templates() -> None:
    """List all loaded prompt templates."""
    from interceptor.template_registry import TemplateRegistry

    registry = TemplateRegistry.load_all()
    items = registry.list_all()

    if not items:
        console.print("[yellow]No templates loaded.[/yellow]")
        return

    table = Table(title="Prompt Templates", show_lines=True)
    table.add_column("Name", style="bold")
    table.add_column("Category")
    table.add_column("Triggers", justify="right")
    table.add_column("Version")

    for t in items:
        trigger_count = len(t.triggers.en) + len(t.triggers.ka)
        table.add_row(
            t.meta.name,
            t.meta.category.value,
            str(trigger_count),
            t.meta.version,
        )

    console.print(table)


@app.command(name="route")
def route_cmd(
    text: str = typer.Argument(help="Input text to route."),
    template: Annotated[
        Optional[str],
        typer.Option("--template", "-t", help="Explicit template name."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON."),
    ] = False,
    file: Annotated[
        Optional[str],
        typer.Option("--file", "-f", help="File path for project context."),
    ] = None,
) -> None:
    """Dry-run routing decision for input text."""
    from interceptor.config import load_config
    from interceptor.routing.models import RouteZone
    from interceptor.routing.router import ProjectContext
    from interceptor.routing.router import route as do_route
    from interceptor.template_registry import TemplateRegistry

    config = load_config()
    registry = TemplateRegistry.load_all()

    context = None
    if file:
        ext = Path(file).suffix.lower() or None
        context = ProjectContext(file_path=file, file_extension=ext)

    try:
        result = do_route(
            text,
            registry,
            config,
            context=context,
            explicit_template=template,
        )
    except ValueError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(code=0) from None

    if json_output:
        console.print(result.model_dump_json(indent=2))
        return

    if result.zone == RouteZone.PASSTHROUGH:
        console.print(
            "[yellow]⚠ No template matched. "
            "Input would be sent as raw prompt.[/yellow]"
        )
        console.print(
            "[dim]Tip: run `mycli templates` to browse available templates[/dim]"
        )
        return

    table = Table(title="Routing Decision", show_lines=True)
    table.add_column("Field", style="bold")
    table.add_column("Value")
    table.add_row("Template", result.template_name or "—")
    table.add_row("Zone", result.zone.value)
    table.add_row("Method", result.method.value)
    table.add_row("Confidence", f"{result.confidence:.4f}")
    table.add_row("Runner-up", result.runner_up or "—")
    console.print(table)

    if result.scores:
        console.print("\n[bold]Top scores:[/bold]")
        top = sorted(result.scores.items(), key=lambda x: x[1], reverse=True)[:5]
        bar_width = 10
        for name, score in top:
            filled = int(score * bar_width)
            bar = "█" * filled + "░" * (bar_width - filled)
            console.print(f"  {name:<20} {bar}  {score:.2f}")

    console.print("[dim]No template applied — dry-run only[/dim]")


@app.command(name="compile")
def compile_cmd(
    text: str = typer.Argument(help="Raw user input to compile."),
    template: Annotated[
        str,
        typer.Option("--template", "-t", help="Template name (required)."),
    ] = ...,
    max_tokens: Annotated[
        int,
        typer.Option("--max-tokens", help="Token budget limit."),
    ] = 8192,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON."),
    ] = False,
) -> None:
    """Dry-run prompt compilation — template + input → compiled prompt."""
    import json as json_mod

    from interceptor.compilation.assembler import compile_prompt
    from interceptor.compilation.cache import CompiledTemplateCache
    from interceptor.template_registry import TemplateRegistry

    registry = TemplateRegistry.load_all()
    tpl = registry.get(template)
    if tpl is None:
        console.print(f"[red]Error: unknown template {template!r}[/red]")
        raise typer.Exit(code=1)

    cache = CompiledTemplateCache()
    cache.warm_template(tpl)

    compiled, budget = compile_prompt(
        template=tpl,
        raw_input=text,
        max_tokens=max_tokens,
        cache=cache,
    )

    if json_output:
        data = {
            "template_name": compiled.template_name,
            "compression_level": compiled.compression_level.value,
            "token_count_estimate": compiled.token_count_estimate,
            "fits": budget.fits,
            "compiled_text": compiled.compiled_text,
        }
        print(json_mod.dumps(data, indent=2, ensure_ascii=False))
        return

    # Rich panel with compiled text.
    from rich.panel import Panel

    console.print(
        Panel(compiled.compiled_text, title="Compiled Prompt", border_style="green")
    )

    # Metadata table.
    table = Table(title="Compilation Metadata", show_lines=True)
    table.add_column("Field", style="bold")
    table.add_column("Value")
    table.add_row("Template", compiled.template_name)
    table.add_row("Compression Level", compiled.compression_level.value)
    table.add_row("Estimated Tokens", str(compiled.token_count_estimate))
    table.add_row("Budget Fits", "✅ yes" if budget.fits else "❌ no")
    table.add_row("Reserve Tokens", str(budget.reserve_tokens))
    table.add_row("Available System Tokens", str(budget.available_system_tokens))
    console.print(table)

    console.print("[dim]Dry-run only — no backend calls made[/dim]")


# ---------------------------------------------------------------------------
# Backend sub-commands
# ---------------------------------------------------------------------------

backend_app = typer.Typer(
    name="backend",
    help="Inspect registered backend adapters.",
    no_args_is_help=True,
)
app.add_typer(backend_app, name="backend")


@backend_app.command(name="list")
def backend_list(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON."),
    ] = False,
) -> None:
    """List all registered backends and their capabilities."""
    import json as json_mod

    from interceptor.adapters.registry import list_backend_capabilities

    caps = list_backend_capabilities()

    if json_output:
        rows = [
            {
                "name": c.name.value,
                "max_tokens": c.max_tokens,
                "supports_system_prompt": c.supports_system_prompt,
                "supports_structured_output": c.supports_structured_output,
                "supports_streaming": c.supports_streaming,
                "temperature_range": [
                    c.temperature_range.minimum,
                    c.temperature_range.maximum,
                ],
                "default_temperature": c.default_temperature,
            }
            for c in caps
        ]
        print(json_mod.dumps(rows, indent=2))
        return

    table = Table(title="Registered Backends", show_lines=True)
    table.add_column("Name", style="bold")
    table.add_column("Max Tokens", justify="right")
    table.add_column("System Prompt")
    table.add_column("Structured Output")
    table.add_column("Streaming")
    table.add_column("Temp Range")

    for c in caps:
        table.add_row(
            c.name.value,
            f"{c.max_tokens:,}",
            "✅" if c.supports_system_prompt else "❌",
            "✅" if c.supports_structured_output else "❌",
            "✅" if c.supports_streaming else "❌",
            f"[{c.temperature_range.minimum}, {c.temperature_range.maximum}]",
        )

    console.print(table)


@backend_app.command(name="inspect")
def backend_inspect(
    name: str = typer.Argument(help="Backend name (e.g. 'claude', 'gpt')."),
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON."),
    ] = False,
) -> None:
    """Show detailed capability info for a single backend."""
    import json as json_mod

    from interceptor.adapters.registry import get_backend_capability

    try:
        cap = get_backend_capability(name)
    except ValueError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(code=1) from None

    data = {
        "name": cap.name.value,
        "max_tokens": cap.max_tokens,
        "supports_system_prompt": cap.supports_system_prompt,
        "supports_structured_output": cap.supports_structured_output,
        "supports_streaming": cap.supports_streaming,
        "temperature_range": [
            cap.temperature_range.minimum,
            cap.temperature_range.maximum,
        ],
        "default_temperature": cap.default_temperature,
    }

    if json_output:
        print(json_mod.dumps(data, indent=2))
        return

    table = Table(title=f"Backend: {cap.name.value}", show_lines=True)
    table.add_column("Property", style="bold")
    table.add_column("Value")
    for key, value in data.items():
        table.add_row(key, str(value))
    console.print(table)


def main() -> None:
    """Console script entry point."""
    app()
