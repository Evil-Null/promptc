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

from interceptor.constants import VERSION

def _lazy_mcp() -> "FastMCP":
    """Import and create FastMCP lazily so --version/--verify skip MCP deps."""
    from mcp.server.fastmcp import FastMCP as _FastMCP
    return _FastMCP("promptc")


# Module-level mcp instance — created lazily on first tool registration
_mcp: "FastMCP | None" = None


def _get_mcp() -> "FastMCP":
    global _mcp  # noqa: PLW0603
    if _mcp is None:
        _mcp = _lazy_mcp()
    return _mcp


# ---------------------------------------------------------------------------
# Warm state — loaded once, shared across all tool calls
# ---------------------------------------------------------------------------

_core: "PromptCompilerCore | None" = None


def _get_core() -> "PromptCompilerCore":
    """Return the shared PromptCompilerCore, creating it on first call."""
    from interceptor.core import PromptCompilerCore as _Core

    global _core  # noqa: PLW0603
    if _core is None:
        _core = _Core()
    return _core


# ---------------------------------------------------------------------------
# Tool functions — module-level for direct import in tests
# ---------------------------------------------------------------------------


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


async def promptc_reload() -> str:
    """Reload promptc configuration, templates, and plugins from disk.

    Call after editing template files or configuration to pick up changes
    without restarting the server.
    """
    core = _get_core()
    await asyncio.to_thread(core.reload)
    return "Reloaded configuration and templates."


def _register_tools() -> None:
    """Register the module-level tool functions on the MCP server."""
    mcp = _get_mcp()
    mcp.tool()(promptc_optimize)
    mcp.tool()(promptc_route)
    mcp.tool()(promptc_templates)
    mcp.tool()(promptc_reload)


# ---------------------------------------------------------------------------
# Verification (--verify flag)
# ---------------------------------------------------------------------------


def _verify() -> int:
    """Run a quick self-test and print results. Returns 0 on success, 1 on failure."""
    import shutil

    checks: list[tuple[str, bool, str]] = []

    checks.append(("version", True, VERSION))

    binary = shutil.which("promptc-mcp")
    checks.append(("binary", binary is not None, binary or "NOT FOUND"))

    try:
        from interceptor.core import PromptCompilerCore as _Core
        core = _Core()
        tpls = core.templates()
        checks.append(("templates", len(tpls) > 0, f"{len(tpls)} loaded"))
    except Exception as exc:
        checks.append(("templates", False, str(exc)))
        core = None

    try:
        if core is None:
            from interceptor.core import PromptCompilerCore as _Core
            core = _Core()
        result = core.route("review this code")
        checks.append(("routing", True, f"zone={result.zone.value}"))
    except Exception as exc:
        checks.append(("routing", False, str(exc)))

    copilot_config = _find_copilot_config()
    if copilot_config and copilot_config.exists():
        registered = _is_registered_in_copilot(copilot_config)
        checks.append(("copilot_config", registered, str(copilot_config)))
    else:
        checks.append(("copilot_config", False, "~/.copilot/config.json not found"))

    all_pass = all(ok for _, ok, _ in checks)

    for name, ok, detail in checks:
        icon = "✅" if ok else "❌"
        print(f"  {icon} {name}: {detail}", file=sys.stderr)

    if all_pass:
        print("\n✅ All checks passed. promptc is ready.", file=sys.stderr)
    else:
        print("\n⚠️  Some checks failed. Run: mycli setup", file=sys.stderr)

    return 0 if all_pass else 1


# ---------------------------------------------------------------------------
# Copilot config helpers (shared with cli.py setup command)
# ---------------------------------------------------------------------------


def _find_copilot_config() -> "Path | None":
    """Locate the Copilot CLI config.json file."""
    from pathlib import Path

    candidates = [
        Path.home() / ".copilot" / "config.json",
        Path.home() / ".config" / "github-copilot" / "config.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def _is_registered_in_copilot(config_path: "Path") -> bool:
    """Check if promptc MCP server is registered in the Copilot config."""
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        return "promptc" in data.get("mcpServers", {})
    except (json.JSONDecodeError, OSError):
        return False


def register_in_copilot(config_path: "Path | None" = None) -> tuple[bool, str]:
    """Register promptc MCP server in Copilot CLI config.json.

    Returns (success, message) tuple.
    """
    from pathlib import Path
    import shutil

    target = config_path or _find_copilot_config()
    if target is None:
        return False, "Cannot find Copilot CLI config directory."

    binary = shutil.which("promptc-mcp")
    if binary is None:
        return False, "promptc-mcp binary not found in PATH."

    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists():
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    else:
        data = {}

    if "promptc" in data.get("mcpServers", {}):
        return True, f"Already registered in {target}"

    data.setdefault("mcpServers", {})
    data["mcpServers"]["promptc"] = {
        "command": binary,
        "args": [],
    }

    target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return True, f"Registered in {target}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Start the MCP server on stdio transport.

    Flags (checked before MCP startup — no stdin required):
      --version   Print version and exit
      --verify    Run self-test diagnostics and exit
    """
    if "--version" in sys.argv:
        print(f"promptc {VERSION}")
        sys.exit(0)

    if "--verify" in sys.argv:
        sys.exit(_verify())

    if "--setup" in sys.argv:
        ok, msg = register_in_copilot()
        print(msg, file=sys.stderr)
        sys.exit(0 if ok else 1)

    from dotenv import load_dotenv

    load_dotenv()

    logging.basicConfig(
        stream=sys.stderr,
        level=logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    _register_tools()
    _get_mcp().run(transport="stdio")
