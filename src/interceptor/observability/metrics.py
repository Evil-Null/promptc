"""Derived metrics — log-driven aggregation over decision records."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class TemplateUsage:
    """Usage count for a single template."""

    name: str
    count: int


@dataclass(slots=True)
class StatsSnapshot:
    """Aggregated metrics derived from decision log records."""

    total_decisions: int = 0
    success_count: int = 0
    error_count: int = 0
    average_execution_time_ms: float | None = None
    retry_rate: float | None = None
    average_gate_score: float | None = None
    average_validation_score: float | None = None
    top_templates: list[TemplateUsage] = field(default_factory=list)


def aggregate(records: list[dict], *, top_n: int = 5) -> StatsSnapshot:
    """Compute a *StatsSnapshot* from raw decision-log dicts.

    Handles missing/malformed fields gracefully — partial records are
    counted where possible and silently skipped for fields they lack.
    """
    total = len(records)
    if total == 0:
        return StatsSnapshot()

    success = 0
    errors = 0
    exec_times: list[int] = []
    retry_count = 0
    gate_scores: list[float] = []
    val_scores: list[float] = []
    tpl_counts: dict[str, int] = {}
    valid = 0

    for rec in records:
        if not isinstance(rec, dict):
            continue
        valid += 1

        outcome = rec.get("outcome", "")
        if outcome == "success":
            success += 1
        elif outcome == "error":
            errors += 1

        et = rec.get("execution_time_ms")
        if isinstance(et, (int, float)) and et >= 0:
            exec_times.append(int(et))

        ra = rec.get("retry_attempts")
        if isinstance(ra, int) and ra > 0:
            retry_count += 1

        gs = rec.get("gate_score")
        if isinstance(gs, (int, float)):
            gate_scores.append(float(gs))

        vs = rec.get("validation_score")
        if isinstance(vs, (int, float)):
            val_scores.append(float(vs))

        tpl = rec.get("selected_template")
        if tpl and isinstance(tpl, str):
            tpl_counts[tpl] = tpl_counts.get(tpl, 0) + 1

    avg_exec = round(sum(exec_times) / len(exec_times), 1) if exec_times else None
    rr = round(retry_count / valid, 4) if valid > 0 else None
    avg_gate = round(sum(gate_scores) / len(gate_scores), 4) if gate_scores else None
    avg_val = round(sum(val_scores) / len(val_scores), 4) if val_scores else None

    top = sorted(tpl_counts.items(), key=lambda x: x[1], reverse=True)[:top_n]
    top_templates = [TemplateUsage(name=n, count=c) for n, c in top]

    return StatsSnapshot(
        total_decisions=valid,
        success_count=success,
        error_count=errors,
        average_execution_time_ms=avg_exec,
        retry_rate=rr,
        average_gate_score=avg_gate,
        average_validation_score=avg_val,
        top_templates=top_templates,
    )
