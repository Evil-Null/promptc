"""Health check logic for config and template validation."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from interceptor.constants import CONFIG_FILE


@dataclass(frozen=True)
class HealthCheckResult:
    """Outcome of a single health check."""

    name: str
    status: Literal["pass", "warn", "fail"]
    message: str
    details: dict[str, str] = field(default_factory=dict)


def check_config_valid(path: Path | None = None) -> HealthCheckResult:
    """Validate the TOML config file at *path*.

    Returns:
        pass  — file exists, parses, and validates.
        warn  — file missing (defaults used) or file invalid (defaults used).
        fail  — impossible internal state (should never occur).
    """
    config_path = path or CONFIG_FILE

    if not config_path.exists():
        return HealthCheckResult(
            name="config_valid",
            status="warn",
            message="No config file found — using compiled-in defaults.",
            details={"path": str(config_path)},
        )

    try:
        raw_text = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        return HealthCheckResult(
            name="config_valid",
            status="warn",
            message=f"Cannot read config file: {exc}. Using defaults.",
            details={"path": str(config_path)},
        )

    try:
        data = tomllib.loads(raw_text)
    except tomllib.TOMLDecodeError as exc:
        return HealthCheckResult(
            name="config_valid",
            status="warn",
            message=f"TOML parse error: {exc}. Using defaults.",
            details={"path": str(config_path)},
        )

    # Import here to avoid circular dependency at module level
    from interceptor.config import Config

    try:
        Config.model_validate(data)
    except ValidationError as exc:
        error_count = len(exc.errors())
        return HealthCheckResult(
            name="config_valid",
            status="warn",
            message=f"Validation: {error_count} error(s). Using defaults.",
            details={"path": str(config_path), "errors": str(exc.errors())},
        )

    return HealthCheckResult(
        name="config_valid",
        status="pass",
        message="Config file is valid.",
        details={"path": str(config_path)},
    )


def check_templates_valid() -> HealthCheckResult:
    """Verify that at least one template is loadable.

    Returns:
        pass — at least one template loaded successfully.
        fail — zero loadable templates (builtin + custom).
    """
    from interceptor.template_registry import TemplateRegistry

    registry = TemplateRegistry.load_all()
    total = registry.count()

    if total == 0:
        return HealthCheckResult(
            name="templates_valid",
            status="fail",
            message="No loadable templates found — check builtin directory.",
        )

    return HealthCheckResult(
        name="templates_valid",
        status="pass",
        message=f"{total} template(s) loaded successfully.",
    )


def check_routing_valid() -> HealthCheckResult:
    """Verify no STRONG trigger phrase is duplicated across templates.

    A "STRONG trigger" is any trigger phrase with ``len >= 6`` chars.
    Collisions are reported as *warn* (informational, not fatal).
    """
    from interceptor.template_registry import TemplateRegistry

    registry = TemplateRegistry.load_all()
    templates = registry.all_templates()

    trigger_owners: dict[str, list[str]] = {}
    for t in templates:
        for phrase in t.triggers.en + t.triggers.ka:
            norm = phrase.strip().lower()
            if len(norm) >= 6:
                trigger_owners.setdefault(norm, []).append(t.meta.name)

    collisions = {
        trigger: owners
        for trigger, owners in trigger_owners.items()
        if len(owners) >= 2
    }

    if not collisions:
        return HealthCheckResult(
            name="routing_valid",
            status="pass",
            message="No trigger collisions detected.",
        )

    detail_parts = [
        f"{trg!r} ({', '.join(owners)})" for trg, owners in collisions.items()
    ]
    return HealthCheckResult(
        name="routing_valid",
        status="warn",
        message=f"Trigger collisions: {'; '.join(detail_parts)}",
    )


def check_compilation_valid() -> HealthCheckResult:
    """Warm all built-in templates through all 5 compression levels.

    Verifies that the assembler succeeds, the compiled prompt is non-empty,
    user-input delimiters are present, and the token estimate is positive.
    """
    from interceptor.compilation.assembler import (
        USER_INPUT_END,
        USER_INPUT_START,
        assemble_compiled_prompt,
    )
    from interceptor.compilation.models import COMPRESSION_ORDER
    from interceptor.template_registry import TemplateRegistry

    registry = TemplateRegistry.load_all()
    templates = registry.all_templates()
    test_input = "health-check probe"
    failures: list[str] = []

    for tpl in templates:
        for level in COMPRESSION_ORDER:
            try:
                result = assemble_compiled_prompt(
                    template=tpl,
                    raw_input=test_input,
                    compression_level=level,
                )
            except Exception as exc:
                failures.append(f"{tpl.meta.name}/{level}: {exc}")
                continue

            if not result.compiled_text:
                failures.append(f"{tpl.meta.name}/{level}: empty compiled text")
            elif USER_INPUT_START not in result.compiled_text:
                failures.append(f"{tpl.meta.name}/{level}: missing start delimiter")
            elif USER_INPUT_END not in result.compiled_text:
                failures.append(f"{tpl.meta.name}/{level}: missing end delimiter")
            elif result.token_count_estimate <= 0:
                failures.append(f"{tpl.meta.name}/{level}: token estimate <= 0")

    if failures:
        return HealthCheckResult(
            name="compilation_valid",
            status="fail",
            message=f"Compilation failures: {'; '.join(failures[:5])}",
        )

    total_checks = len(templates) * len(COMPRESSION_ORDER)
    return HealthCheckResult(
        name="compilation_valid",
        status="pass",
        message=f"All {total_checks} template×level combinations compile OK.",
    )
