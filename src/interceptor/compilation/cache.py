"""In-memory cache for precompiled template compression variants."""

from __future__ import annotations

from typing import TYPE_CHECKING

from interceptor.compilation.compressor import build_template_sections, compress_sections
from interceptor.compilation.models import COMPRESSION_ORDER, CompressionLevel

if TYPE_CHECKING:
    from interceptor.models.template import Template


class CompiledTemplateCache:
    """Cache compressed section variants for all 5 compression levels."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, CompressionLevel], dict[str, str]] = {}

    def warm_template(self, template: Template) -> None:
        """Precompute compressed sections for all 5 levels.  Idempotent."""
        raw_sections = build_template_sections(template)
        for level in COMPRESSION_ORDER:
            key = (template.meta.name, level)
            compressed, _ = compress_sections(raw_sections, level)
            self._store[key] = compressed

    def get(
        self, template_name: str, level: CompressionLevel
    ) -> dict[str, str] | None:
        """Return cached sections or ``None`` if not warmed."""
        return self._store.get((template_name, level))

    def count(self) -> int:
        """Number of cached entries (template × level pairs)."""
        return len(self._store)

    def clear(self) -> None:
        """Remove all cached entries."""
        self._store.clear()
