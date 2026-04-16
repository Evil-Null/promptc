"""Tests for __main__.py entry point and audit code-quality fixes."""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"


class TestMainEntry:
    """Verify python -m interceptor entry point."""

    def test_main_module_exists(self) -> None:
        main_path = (
            PROJECT_ROOT / "src" / "interceptor" / "__main__.py"
        )
        assert main_path.exists()
        content = main_path.read_text(encoding="utf-8")
        assert "from interceptor.cli import main" in content
        assert "main()" in content

    def test_python_m_interceptor_version(self) -> None:
        result = subprocess.run(
            [str(VENV_PYTHON), "-m", "interceptor", "version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "1.3.0" in result.stdout


class TestCodeQualityFixes:
    """Verify audit-driven code quality improvements."""

    def test_no_magic_temperature_in_cli(self) -> None:
        cli_path = PROJECT_ROOT / "src" / "interceptor" / "cli.py"
        content = cli_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if "temperature=" in stripped and "0.7" in stripped:
                if stripped.startswith(("#", "_DEFAULT", "def ", "\"", "'")):
                    continue
                if "_DEFAULT_TEMPERATURE" in stripped:
                    continue
                pytest.fail(
                    f"Magic number temperature=0.7 at cli.py:{i}: {stripped}"
                )

    def test_no_magic_max_tokens_in_cli(self) -> None:
        cli_path = PROJECT_ROOT / "src" / "interceptor" / "cli.py"
        content = cli_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if "max_output_tokens=" in stripped and "4096" in stripped:
                if stripped.startswith(("#", "_DEFAULT", "def ", "\"", "'")):
                    continue
                if "_DEFAULT_MAX_OUTPUT_TOKENS" in stripped:
                    continue
                pytest.fail(
                    f"Magic number max_output_tokens=4096 at cli.py:{i}: {stripped}"
                )

    def test_decision_log_has_logger(self) -> None:
        dl_path = (
            PROJECT_ROOT / "src" / "interceptor" / "observability" / "decision_log.py"
        )
        content = dl_path.read_text(encoding="utf-8")
        assert "import logging" in content
        assert "_logger" in content

    def test_no_bare_exception_pass_in_decision_log(self) -> None:
        dl_path = (
            PROJECT_ROOT / "src" / "interceptor" / "observability" / "decision_log.py"
        )
        content = dl_path.read_text(encoding="utf-8")
        assert "except Exception:\n        pass" not in content

    def test_selector_no_unused_backendname(self) -> None:
        sel_path = (
            PROJECT_ROOT / "src" / "interceptor" / "adapters" / "selector.py"
        )
        content = sel_path.read_text(encoding="utf-8")
        assert "BackendName" not in content

    def test_retry_engine_no_unused_strictness_order(self) -> None:
        re_path = (
            PROJECT_ROOT / "src" / "interceptor" / "validation" / "retry_engine.py"
        )
        content = re_path.read_text(encoding="utf-8")
        assert "STRICTNESS_ORDER" not in content
