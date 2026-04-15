"""PR-33 tests — v1.0.0 release proof."""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


# ── A: Version consistency ───────────────────────────────────────────


class TestVersionConsistency:
    """Version string 1.0.0 in all canonical locations."""

    def test_constants_version(self):
        from interceptor.constants import VERSION

        assert VERSION == "1.0.0"

    def test_pyproject_version(self):
        text = (ROOT / "pyproject.toml").read_text()
        match = re.search(r'^version\s*=\s*"(.+?)"', text, re.MULTILINE)
        assert match is not None
        assert match.group(1) == "1.0.0"

    def test_cli_version_output(self):
        from typer.testing import CliRunner

        from interceptor.cli import app

        result = CliRunner().invoke(app, ["version"])
        assert result.exit_code == 0
        assert "1.0.0" in result.output


# ── B: Release artifacts exist ───────────────────────────────────────


class TestReleaseArtifacts:
    """All required release files present."""

    def test_readme_exists(self):
        assert (ROOT / "README.md").exists()
        content = (ROOT / "README.md").read_text()
        assert len(content) > 200, "README too short"

    def test_changelog_exists(self):
        assert (ROOT / "CHANGELOG.md").exists()
        content = (ROOT / "CHANGELOG.md").read_text()
        assert "1.0.0" in content

    def test_license_exists(self):
        assert (ROOT / "LICENSE").exists()
        content = (ROOT / "LICENSE").read_text()
        assert "MIT" in content

    def test_py_typed_exists(self):
        assert (ROOT / "src" / "interceptor" / "py.typed").exists()

    def test_pyproject_has_mit_license(self):
        text = (ROOT / "pyproject.toml").read_text()
        assert "MIT" in text


# ── C: Package importability ─────────────────────────────────────────


class TestPackageImportability:
    """All public modules import cleanly."""

    MODULES = [
        "interceptor.cli",
        "interceptor.config",
        "interceptor.constants",
        "interceptor.health",
        "interceptor.models",
        "interceptor.template_registry",
        "interceptor.routing.router",
        "interceptor.compilation.assembler",
        "interceptor.observability.decision_log",
        "interceptor.observability.models",
        "interceptor.plugins.registry",
    ]

    @pytest.mark.parametrize("module", MODULES)
    def test_module_imports(self, module):
        importlib.import_module(module)


# ── D: Full suite count proof ────────────────────────────────────────


class TestSuiteIntegrity:
    """Suite has expected minimum test count."""

    def test_minimum_test_count(self):
        """At least 1180 tests exist (guards against accidental deletion)."""
        import subprocess

        result = subprocess.run(
            [
                str(ROOT / ".venv" / "bin" / "python"),
                "-m",
                "pytest",
                "--collect-only",
                "-q",
            ],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        last_line = [l for l in result.stdout.strip().splitlines() if "test" in l][-1]
        count = int(re.search(r"(\d+)", last_line).group(1))
        assert count >= 1180, f"Only {count} tests found, expected ≥1180"
