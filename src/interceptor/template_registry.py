"""In-memory template registry with builtin + custom discovery."""

from __future__ import annotations

from pathlib import Path

from interceptor.constants import TEMPLATES_BUILTIN_DIR, TEMPLATES_CUSTOM_DIR
from interceptor.models.template import Template
from interceptor.template_loader import load_template


class TemplateRegistry:
    """Registry for all loaded templates (builtin + custom)."""

    def __init__(self, templates: dict[str, Template] | None = None) -> None:
        self._templates: dict[str, Template] = templates or {}

    @classmethod
    def load_all(cls) -> TemplateRegistry:
        """Discover and load all templates.

        Discovery order (higher priority wins on name collision):
            1. Built-in templates (package-shipped)
            2. Custom templates (~/.config/interceptor/templates/custom)
        """
        templates: dict[str, Template] = {}
        _load_dir(TEMPLATES_BUILTIN_DIR, templates)
        _load_dir(TEMPLATES_CUSTOM_DIR, templates)
        return cls(templates)

    def get(self, name: str) -> Template | None:
        """Return a template by name, or None."""
        return self._templates.get(name)

    def all_templates(self) -> list[Template]:
        """Return all loaded templates (unsorted, for internal indexing)."""
        return list(self._templates.values())

    def list_all(self) -> list[Template]:
        """Return all loaded templates (sorted by name for determinism)."""
        return sorted(self._templates.values(), key=lambda t: t.meta.name)

    def count(self) -> int:
        """Return the number of loaded templates."""
        return len(self._templates)


def _load_dir(directory: Path, target: dict[str, Template]) -> None:
    """Load all .toml files from *directory* into *target* dict."""
    if not directory.is_dir():
        return
    for toml_file in sorted(directory.glob("*.toml")):
        template = load_template(toml_file)
        if template is not None:
            target[template.meta.name] = template
