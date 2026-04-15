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
    check_config_valid,
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


def main() -> None:
    """Console script entry point."""
    app()
