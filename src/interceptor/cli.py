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


# ---------------------------------------------------------------------------
# Validation display helper
# ---------------------------------------------------------------------------


def _render_validation(validation: object) -> None:
    """Print non-passing validation result to the terminal."""
    status = getattr(validation, "status", "")
    score = getattr(validation, "score", 0.0)
    issues = getattr(validation, "issues", [])

    tag = (
        f"[yellow]⚠ validation: {status} ({score:.0%})[/yellow]"
        if status == "partial"
        else f"[red]⚠ validation: {status} ({score:.0%})[/red]"
    )
    console.print(tag)
    for issue in issues:
        console.print(f"  [dim]- {issue.message}[/dim]")


def _render_gate_evaluation(gate_eval: object) -> None:
    """Print gate evaluation results to terminal."""
    hard_passed = getattr(gate_eval, "hard_passed", True)
    gate_score = getattr(gate_eval, "gate_score", 1.0)
    failures = getattr(gate_eval, "failures", [])
    warnings = getattr(gate_eval, "warnings", [])

    if failures:
        console.print(
            f"[red]✘ quality gates: FAIL ({gate_score:.0%})[/red]"
        )
        for f in failures:
            console.print(f"  [red]- {f.gate_text}[/red]")
            if f.detail:
                console.print(f"    [dim]{f.detail}[/dim]")
    if warnings:
        console.print("[yellow]⚠ quality gate warnings:[/yellow]")
        for w in warnings:
            console.print(f"  [dim]- {w.gate_text}[/dim]")


def _render_retry_result(retry: object) -> None:
    """Print retry outcome to terminal."""
    outcome = getattr(retry, "outcome", "not_needed")
    attempts = getattr(retry, "attempts", 1)
    same_failure = getattr(retry, "same_failure_stopped", False)

    if str(outcome) == "recovered":
        console.print(
            f"[green]✓ recovered after {attempts} attempt(s)[/green]"
        )
    elif str(outcome) == "exhausted":
        if same_failure:
            console.print(
                f"[yellow]⚠ retry stopped (same failure) after {attempts} attempt(s)[/yellow]"
            )
        else:
            console.print(
                f"[yellow]⚠ retry exhausted after {attempts} attempt(s)[/yellow]"
            )


def _log_execution(
    config: object,
    raw_input: str,
    template_name: str,
    backend: str,
    elapsed_ms: int,
    *,
    result: object | None = None,
    error: str | None = None,
) -> None:
    """Build and emit a decision record.  Fire-and-forget — never raises."""
    try:
        enabled = getattr(
            getattr(config, "observability", None), "decision_logging", False
        )
        if not enabled:
            return

        from interceptor.observability.decision_log import log_decision
        from interceptor.observability.models import DecisionRecord

        record = DecisionRecord(
            input_hash=DecisionRecord.hash_input(raw_input),
            selected_template=template_name,
            backend=backend,
            execution_time_ms=elapsed_ms,
        )

        if error:
            record.outcome = "error"
            record.error = error
        elif result is not None:
            record.finish_reason = getattr(result, "finish_reason", None)
            record.usage_input_tokens = getattr(result, "usage_input_tokens", None)
            record.usage_output_tokens = getattr(result, "usage_output_tokens", None)

            val = getattr(result, "validation", None)
            if val:
                record.validation_status = str(getattr(val, "status", ""))
                record.validation_score = getattr(val, "score", None)

            gate = getattr(result, "gate_evaluation", None)
            if gate:
                record.gate_score = getattr(gate, "gate_score", None)
                record.gate_hard_passed = getattr(gate, "hard_passed", None)

            retry = getattr(result, "retry_result", None)
            if retry:
                record.retry_attempts = getattr(retry, "attempts", None)
                record.retry_outcome = str(getattr(retry, "outcome", ""))

        log_decision(record)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Run (compile + adapt dry-run)
# ---------------------------------------------------------------------------


@app.command()
def run(
    text: Annotated[str, typer.Argument(help="User input text.")],
    template: Annotated[
        str,
        typer.Option("--template", "-t", help="Template name."),
    ] = "",
    backend: Annotated[
        str,
        typer.Option("--backend", "-b", help="Backend name (claude, gpt)."),
    ] = "",
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show adapted request without network calls."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON."),
    ] = False,
    stream: Annotated[
        bool,
        typer.Option("--stream", help="Stream response tokens to terminal."),
    ] = False,
) -> None:
    """Compile, route, and adapt a prompt. Use --dry-run to inspect without sending."""
    import json as json_mod

    from interceptor.adapters.selector import select_backend
    from interceptor.adapters.service import AdapterService
    from interceptor.compilation.assembler import compile_prompt
    from interceptor.config import load_config
    from interceptor.routing.router import route as do_route
    from interceptor.template_registry import TemplateRegistry

    if stream and json_output:
        console.print("[red]Error:[/red] --stream and --json cannot be used together.")
        raise typer.Exit(code=1)

    config = load_config()
    registry = TemplateRegistry.load_all()

    if template:
        tpl = registry.get(template)
        if tpl is None:
            console.print(f"[red]Error:[/red] Unknown template {template!r}")
            raise typer.Exit(code=1)
    else:
        decision = do_route(text, registry, config)
        if decision.template is None:
            console.print("[red]Error:[/red] No template matched.")
            raise typer.Exit(code=1)
        tpl = decision.template
        template = tpl.meta.name

    # Compile.
    compiled, _budget = compile_prompt(template=tpl, raw_input=text)

    # Select backend.
    if backend:
        backend_name = backend
    else:
        cap = select_backend()
        backend_name = cap.name.value

    service = AdapterService()

    if dry_run:
        # Dry-run path — adapt and display without sending.
        request = service.adapt_request(
            backend=backend_name,
            compiled_prompt=compiled,
            temperature=0.7,
            max_output_tokens=4096,
            stream=stream,
        )

        if json_output:
            data = {
                "template": template,
                "backend": request.backend.value,
                "temperature": request.temperature,
                "max_output_tokens": request.max_output_tokens,
                "streaming": request.streaming,
                "payload": request.payload,
                "system_text_length": len(request.payload.get("system", request.payload.get("messages", [{}])[0].get("content", ""))),
                "user_text_length": len(request.payload.get("messages", [{}])[-1].get("content", "")),
            }
            print(json_mod.dumps(data, indent=2, ensure_ascii=False))
            return

        from rich.panel import Panel

        system_text = request.payload.get("system", "")
        if not system_text:
            msgs = request.payload.get("messages", [])
            system_text = msgs[0].get("content", "") if msgs else ""
        user_text = request.payload.get("messages", [{}])[-1].get("content", "")

        console.print(Panel(system_text[:500], title="System Content (preview)", border_style="cyan"))
        console.print(Panel(user_text[:500], title="User Content (preview)", border_style="green"))

        table = Table(title="Adapted Request Metadata", show_lines=True)
        table.add_column("Field", style="bold")
        table.add_column("Value")
        table.add_row("Template", template)
        table.add_row("Backend", request.backend.value)
        table.add_row("Temperature", str(request.temperature))
        table.add_row("Max Output Tokens", str(request.max_output_tokens))
        table.add_row("Streaming", str(request.streaming))
        table.add_row("System Content Length", str(len(system_text)))
        table.add_row("User Content Length", str(len(user_text)))
        console.print(table)

        console.print("[dim]Dry-run only — no network calls made[/dim]")
        return

    if stream:
        # Streaming execution path — progressive terminal passthrough.
        try:
            events = service.execute_stream(
                backend=backend_name,
                compiled_prompt=compiled,
                temperature=0.7,
                max_output_tokens=4096,
            )
            for event in events:
                if event.done:
                    break
                sys.stdout.write(event.text)
                sys.stdout.flush()
            sys.stdout.write("\n")
            sys.stdout.flush()
        except Exception as exc:
            console.print(f"\n[red]Error:[/red] {exc}")
            raise typer.Exit(code=1) from exc
        return

    # Non-streaming execution path — send to backend API.
    import time as time_mod

    start_ns = time_mod.monotonic()
    try:
        result = service.execute_full(
            backend=backend_name,
            compiled_prompt=compiled,
            temperature=0.7,
            max_output_tokens=4096,
        )
    except Exception as exc:
        elapsed_ms = int((time_mod.monotonic() - start_ns) * 1000)
        _log_execution(config, text, template, backend_name, elapsed_ms, error=str(exc))
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    elapsed_ms = int((time_mod.monotonic() - start_ns) * 1000)
    _log_execution(config, text, template, backend_name, elapsed_ms, result=result)

    if json_output:
        data = {
            "template": template,
            "backend": result.backend,
            "finish_reason": result.finish_reason,
            "usage_input_tokens": result.usage_input_tokens,
            "usage_output_tokens": result.usage_output_tokens,
            "text": result.text,
        }
        if result.validation:
            data["validation"] = {
                "status": result.validation.status.value,
                "score": result.validation.score,
                "validator": result.validation.validator_name,
                "issues": [
                    {"rule": i.rule, "message": i.message}
                    for i in result.validation.issues
                ],
            }
        if result.gate_evaluation:
            data["gate_evaluation"] = {
                "hard_passed": result.gate_evaluation.hard_passed,
                "gate_score": result.gate_evaluation.gate_score,
                "passed_hard_gates": result.gate_evaluation.passed_hard_gates,
                "total_hard_gates": result.gate_evaluation.total_hard_gates,
                "failures": [
                    {"gate": r.gate_text, "evaluator": r.evaluator, "detail": r.detail}
                    for r in result.gate_evaluation.failures
                ],
                "warnings": [
                    {"gate": r.gate_text, "evaluator": r.evaluator, "detail": r.detail}
                    for r in result.gate_evaluation.warnings
                ],
            }
        if result.retry_result and str(result.retry_result.outcome) != "not_needed":
            data["retry"] = {
                "attempts": result.retry_result.attempts,
                "max_retries": result.retry_result.max_retries,
                "outcome": str(result.retry_result.outcome),
                "final_strictness": str(result.retry_result.final_strictness) if result.retry_result.final_strictness else None,
                "same_failure_stopped": result.retry_result.same_failure_stopped,
                "failure_reasons": [str(r) for r in result.retry_result.failure_reasons],
            }
        print(json_mod.dumps(data, indent=2, ensure_ascii=False))
        return

    console.print(result.text)
    console.print(
        f"\n[dim]{result.backend} · {result.finish_reason} · "
        f"in={result.usage_input_tokens} out={result.usage_output_tokens}[/dim]"
    )

    if result.validation and result.validation.status != "pass":
        _render_validation(result.validation)

    if result.gate_evaluation and (
        not result.gate_evaluation.hard_passed or result.gate_evaluation.warnings
    ):
        _render_gate_evaluation(result.gate_evaluation)

    if result.retry_result:
        _render_retry_result(result.retry_result)


# ---------------------------------------------------------------------------
# Logs (decision log reader + prune)
# ---------------------------------------------------------------------------

logs_app = typer.Typer(name="logs", help="Decision log commands.")
app.add_typer(logs_app)


@logs_app.callback(invoke_without_command=True)
def logs(
    ctx: typer.Context,
    count: Annotated[
        int,
        typer.Option("--count", "-n", help="Number of recent entries."),
    ] = 10,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON."),
    ] = False,
) -> None:
    """Show today's decision log entries."""
    if ctx.invoked_subcommand is not None:
        return

    import json as json_mod
    from datetime import date

    from interceptor.observability.decision_log import read_daily_log

    records = read_daily_log()
    total = len(records)
    recent = records[-count:] if count < total else records

    if json_output:
        print(json_mod.dumps({
            "date": date.today().isoformat(),
            "total": total,
            "showing": len(recent),
            "entries": recent,
        }, indent=2, ensure_ascii=False))
        return

    console.print(f"[bold]Decision log — {date.today().isoformat()}[/bold]")
    console.print(f"Total entries: {total}")

    if not records:
        console.print("[dim]No entries yet.[/dim]")
        return

    table = Table(show_lines=False)
    table.add_column("Time", style="dim", max_width=19)
    table.add_column("Template")
    table.add_column("Backend")
    table.add_column("Outcome")
    table.add_column("Tokens", justify="right")
    table.add_column("Retry")

    for rec in recent:
        ts = rec.get("timestamp", "")[:19]
        tpl = rec.get("selected_template", "—")
        bk = rec.get("backend", "—")
        out = rec.get("outcome", "—")
        tok_in = rec.get("usage_input_tokens") or 0
        tok_out = rec.get("usage_output_tokens") or 0
        tokens = f"{tok_in}→{tok_out}"
        retry_a = rec.get("retry_attempts")
        retry_o = rec.get("retry_outcome", "")
        retry_str = f"{retry_a}×{retry_o}" if retry_a and retry_o != "not_needed" else "—"

        style = "green" if out == "success" else "red"
        table.add_row(ts, tpl, bk, f"[{style}]{out}[/{style}]", tokens, retry_str)

    console.print(table)


@logs_app.command()
def prune(
    before: Annotated[
        str,
        typer.Option("--before", help="Prune logs strictly older than YYYY-MM-DD."),
    ],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what would be deleted without deleting."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON."),
    ] = False,
) -> None:
    """Prune old decision log files."""
    import json as json_mod
    from datetime import date

    from interceptor.constants import LOG_DIR
    from interceptor.observability.log_prune import prune_logs_before

    try:
        cutoff = date.fromisoformat(before)
    except ValueError:
        console.print(f"[red]Invalid date:[/red] {before}")
        raise typer.Exit(code=1)

    result = prune_logs_before(LOG_DIR, cutoff, dry_run=dry_run)

    if json_output:
        import dataclasses

        print(json_mod.dumps(dataclasses.asdict(result), indent=2))
        return

    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    console.print(f"{prefix}[bold]Log prune — before {before}[/bold]")
    console.print(f"  Scanned    : {result.files_scanned} log files")
    console.print(f"  Deleted    : {result.files_deleted}")
    console.print(f"  Freed      : {result.bytes_freed} bytes")
    if result.skipped_files:
        console.print(f"  Skipped    : {result.skipped_files} non-log files")


# ---------------------------------------------------------------------------
# Stats (derived metrics)
# ---------------------------------------------------------------------------


@app.command()
def stats(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON."),
    ] = False,
    date_str: Annotated[
        Optional[str],
        typer.Option("--date", help="Date in YYYY-MM-DD format (default: today)."),
    ] = None,
) -> None:
    """Show derived metrics for a day's decision log."""
    import json as json_mod
    from datetime import date

    from interceptor.observability.decision_log import read_daily_log
    from interceptor.observability.metrics import aggregate

    day: date | None = None
    if date_str:
        try:
            day = date.fromisoformat(date_str)
        except ValueError:
            console.print(f"[red]Invalid date:[/red] {date_str}")
            raise typer.Exit(code=1)

    records = read_daily_log(day)
    snap = aggregate(records)

    if json_output:
        print(json_mod.dumps({
            "date": (day or date.today()).isoformat(),
            "total_decisions": snap.total_decisions,
            "success_count": snap.success_count,
            "error_count": snap.error_count,
            "average_execution_time_ms": snap.average_execution_time_ms,
            "retry_rate": snap.retry_rate,
            "average_gate_score": snap.average_gate_score,
            "average_validation_score": snap.average_validation_score,
            "top_templates": [
                {"name": t.name, "count": t.count} for t in snap.top_templates
            ],
        }, indent=2, ensure_ascii=False))
        return

    label = (day or date.today()).isoformat()
    console.print(f"[bold]Stats — {label}[/bold]")

    if snap.total_decisions == 0:
        console.print("[dim]No decisions recorded.[/dim]")
        return

    console.print(f"  Decisions  : {snap.total_decisions}")
    console.print(
        f"  Success    : {snap.success_count}  "
        f"Errors: {snap.error_count}"
    )
    if snap.average_execution_time_ms is not None:
        console.print(f"  Avg time   : {snap.average_execution_time_ms} ms")
    if snap.retry_rate is not None:
        console.print(f"  Retry rate : {snap.retry_rate:.2%}")
    if snap.average_validation_score is not None:
        console.print(f"  Avg schema : {snap.average_validation_score:.4f}")
    if snap.average_gate_score is not None:
        console.print(f"  Avg gate   : {snap.average_gate_score:.4f}")

    if snap.top_templates:
        console.print("\n  [bold]Top templates:[/bold]")
        for t in snap.top_templates:
            console.print(f"    {t.count:>4}× {t.name}")


def main() -> None:
    """Console script entry point."""
    app()
