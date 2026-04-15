"""TOML template loader with structural validation."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

from pydantic import ValidationError

from interceptor.models.template import Template

_REQUIRED_SECTIONS = ("meta", "triggers", "prompt")


def validate_template(data: dict) -> list[str]:
    """Validate raw dict against Template schema.

    Returns a list of error strings.  Empty list means valid.
    """
    errors: list[str] = []

    for section in _REQUIRED_SECTIONS:
        if section not in data:
            errors.append(f"Missing required section: [{section}]")

    if errors:
        return errors

    try:
        Template.model_validate(data)
    except ValidationError as exc:
        for err in exc.errors():
            loc = " → ".join(str(p) for p in err["loc"])
            errors.append(f"{loc}: {err['msg']}")

    return errors


def load_template(path: Path) -> Template | None:
    """Load and validate a single template TOML file.

    Returns Template on success, None on any failure.  Never raises.
    """
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"⚠️  Cannot read template {path}: {exc}", file=sys.stderr)
        return None

    try:
        data = tomllib.loads(raw_text)
    except tomllib.TOMLDecodeError as exc:
        print(f"⚠️  TOML parse error in {path}: {exc}", file=sys.stderr)
        return None

    errors = validate_template(data)
    if errors:
        joined = "; ".join(errors)
        print(
            f"⚠️  Template validation failed for {path}: {joined}",
            file=sys.stderr,
        )
        return None

    return Template.model_validate(data)
