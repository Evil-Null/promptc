"""Sample reference plugin — trailing-whitespace normalizer.

Demonstrates the minimal plugin contract for interceptor's plugin system.
Implements a single ``prevalidate`` hook that strips trailing whitespace
from each line of the backend response before schema validation runs.

Hook interface::

    prevalidate(text: str, ctx: PluginContext) -> str
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from interceptor.plugins.context import PluginContext


class Plugin:
    """Normalize trailing whitespace in backend output before validation."""

    def prevalidate(self, text: str, ctx: PluginContext) -> str:
        """Strip trailing whitespace from each line."""
        return "\n".join(line.rstrip() for line in text.split("\n"))
