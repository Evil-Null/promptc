"""Plugin discovery — scan canonical directory and validate manifests."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

from pydantic import ValidationError

from interceptor.plugins.models import DiscoveredPlugin, PluginManifest


def load_plugin_manifest(plugin_dir: Path) -> PluginManifest | None:
    """Load and validate plugin.toml from a plugin directory.

    Returns PluginManifest on success, None on any failure.  Never raises.
    """
    toml_path = plugin_dir / "plugin.toml"

    if not toml_path.is_file():
        return None

    try:
        raw = toml_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(
            f"⚠️  Cannot read {toml_path}: {exc}",
            file=sys.stderr,
        )
        return None

    try:
        data = tomllib.loads(raw)
    except tomllib.TOMLDecodeError as exc:
        print(
            f"⚠️  TOML parse error in {toml_path}: {exc}",
            file=sys.stderr,
        )
        return None

    try:
        return PluginManifest.model_validate(data)
    except ValidationError as exc:
        errors = "; ".join(
            f"{' → '.join(str(p) for p in e['loc'])}: {e['msg']}"
            for e in exc.errors()
        )
        print(
            f"⚠️  Invalid plugin manifest {toml_path}: {errors}",
            file=sys.stderr,
        )
        return None


def discover_plugins(
    plugins_dir: Path,
) -> tuple[list[DiscoveredPlugin], list[str]]:
    """Discover all valid plugins under *plugins_dir*.

    Layout expected::

        plugins_dir/
            plugin-a/
                plugin.toml
            plugin-b/
                plugin.toml

    Returns (valid_plugins, warnings).
    First valid plugin wins on duplicate names; later duplicates are skipped.
    """
    warnings: list[str] = []
    plugins: list[DiscoveredPlugin] = []
    seen_names: set[str] = set()

    if not plugins_dir.is_dir():
        return plugins, warnings

    for child in sorted(plugins_dir.iterdir()):
        if not child.is_dir():
            continue

        manifest = load_plugin_manifest(child)
        if manifest is None:
            warnings.append(f"Skipped {child.name}: invalid or missing plugin.toml")
            continue

        if manifest.name in seen_names:
            warnings.append(
                f"Skipped {child.name}: duplicate plugin name {manifest.name!r}"
            )
            continue

        seen_names.add(manifest.name)
        plugins.append(DiscoveredPlugin(manifest=manifest, path=child))

    return plugins, warnings
