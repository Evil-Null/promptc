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
