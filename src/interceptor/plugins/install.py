"""Plugin install/uninstall helpers — minimal distribution proof."""

from __future__ import annotations

import shutil
from pathlib import Path


def install_plugin(source_dir: Path, plugins_dir: Path) -> Path:
    """Copy a plugin directory into the canonical plugins location.

    Returns the installed plugin path.
    Raises FileExistsError if the target directory already exists.
    Raises FileNotFoundError if source_dir does not exist.
    """
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Source not found: {source_dir}")

    target = plugins_dir / source_dir.name
    if target.exists():
        raise FileExistsError(f"Plugin already installed at {target}")

    plugins_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, target)
    return target


def uninstall_plugin(name: str, plugins_dir: Path) -> bool:
    """Remove an installed plugin by directory name.

    Returns True if removed, False if not found.
    """
    target = plugins_dir / name
    if not target.is_dir():
        return False
    shutil.rmtree(target)
    return True
