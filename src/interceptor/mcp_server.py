"""MCP (Model Context Protocol) server exposing promptc as Copilot CLI tools.

Runs as a stdio subprocess managed by the MCP host (e.g. GitHub Copilot CLI).
All synchronous pipeline work is offloaded via ``asyncio.to_thread`` to keep
the event loop responsive.

Entry point: ``promptc-mcp`` (registered in pyproject.toml).
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys

from mcp.server.fastmcp import FastMCP

from interceptor.core import PromptCompilerCore

mcp = FastMCP("promptc")

# ---------------------------------------------------------------------------
# Warm state — loaded once, shared across all tool calls
# ---------------------------------------------------------------------------

_core: PromptCompilerCore | None = None


def _get_core() -> PromptCompilerCore:
    """Return the shared PromptCompilerCore, creating it on first call."""
    global _core  # noqa: PLW0603
    if _core is None:
        _core = PromptCompilerCore()
    return _core


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def promptc_optimize(text: str, template: str | None = None) -> str:
    """Optimize a prompt using promptc templates.

    Returns an enhanced system prompt that the AI agent should use
    to guide its response. This is the primary tool — call it with
    any user query to get a template-enhanced prompt.
    """
    core = _get_core()
    try:
        compiled, _budget = await asyncio.to_thread(
            core.compile, text, template=template,
        )
        return compiled.compiled_text
    except ValueError as exc:
        return f"[promptc] {exc}"


@mcp.tool()
async def promptc_route(text: str) -> str:
    """Analyze text and determine which promptc template matches best.

    Returns JSON with template name, confidence score, routing zone,
    and routing method.
    """
    core = _get_core()
    result = await asyncio.to_thread(core.route, text)
    return json.dumps(
        {
            "template": result.template_name,
            "confidence": result.confidence,
            "zone": result.zone.value,
            "method": result.method.value,
        },
        ensure_ascii=False,
    )


@mcp.tool()
async def promptc_templates() -> str:
    """List all available prompt optimization templates.

    Returns JSON array with template name, category, and version.
    """
    core = _get_core()
    templates = core.templates()
    return json.dumps(
        [
            {
                "name": t.meta.name,
                "category": t.meta.category.value,
                "version": t.meta.version,
            }
            for t in templates
        ],
        ensure_ascii=False,
    )


@mcp.tool()
async def promptc_reload() -> str:
    """Reload promptc configuration, templates, and plugins from disk.

    Call after editing template files or configuration to pick up changes
    without restarting the server.
    """
    core = _get_core()
    await asyncio.to_thread(core.reload)
    return "Reloaded configuration and templates."


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Start the MCP server on stdio transport."""
    from dotenv import load_dotenv

    load_dotenv()

    # CRITICAL: redirect ALL logging to stderr so stdout stays clean
    # for the MCP JSON-RPC protocol.
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    mcp.run(transport="stdio")
