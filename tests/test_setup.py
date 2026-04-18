"""Tests for promptc-mcp CLI flags (--version, --verify, --setup) and setup helpers."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from interceptor.constants import VERSION
from interceptor.mcp_server import (
    _find_copilot_config,
    _is_registered_in_copilot,
    register_in_copilot,
)


class TestMcpVersion:
    """Tests for ``promptc-mcp --version``."""

    def test_version_flag_prints_version(self) -> None:
        from interceptor.mcp_server import main

        with patch("sys.argv", ["promptc-mcp", "--version"]):
            with patch("builtins.print") as mock_print:
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 0
                mock_print.assert_called_once()
                assert VERSION in mock_print.call_args[0][0]

    def test_version_flag_exits_zero(self) -> None:
        from interceptor.mcp_server import main

        with patch("sys.argv", ["promptc-mcp", "--version"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0


class TestMcpVerify:
    """Tests for ``promptc-mcp --verify``."""

    def test_verify_runs_checks(self) -> None:
        from interceptor.mcp_server import _verify

        with patch("shutil.which", return_value="/usr/bin/promptc-mcp"):
            with patch(
                "interceptor.mcp_server._find_copilot_config",
                return_value=None,
            ):
                exit_code = _verify()
                assert isinstance(exit_code, int)


class TestCopilotConfigHelpers:
    """Tests for Copilot config discovery and registration."""

    def test_find_copilot_config_returns_path(self, tmp_path: Path) -> None:
        config = tmp_path / ".copilot" / "mcp-config.json"
        config.parent.mkdir(parents=True)
        config.write_text("{}", encoding="utf-8")

        with patch("pathlib.Path.home", return_value=tmp_path):
            result = _find_copilot_config()
            assert result is not None
            assert result.name == "mcp-config.json"

    def test_find_copilot_config_returns_default_when_missing(
        self, tmp_path: Path
    ) -> None:
        with patch("pathlib.Path.home", return_value=tmp_path):
            result = _find_copilot_config()
            assert result is not None
            assert "mcp-config.json" in str(result)

    def test_is_registered_true(self, tmp_path: Path) -> None:
        config = tmp_path / "mcp-config.json"
        config.write_text(
            json.dumps({"mcpServers": {"promptc": {"command": "x"}}}),
            encoding="utf-8",
        )
        assert _is_registered_in_copilot(config) is True

    def test_is_registered_false_empty(self, tmp_path: Path) -> None:
        config = tmp_path / "mcp-config.json"
        config.write_text("{}", encoding="utf-8")
        assert _is_registered_in_copilot(config) is False

    def test_is_registered_false_no_promptc(self, tmp_path: Path) -> None:
        config = tmp_path / "mcp-config.json"
        config.write_text(
            json.dumps({"mcpServers": {"other": {}}}),
            encoding="utf-8",
        )
        assert _is_registered_in_copilot(config) is False

    def test_is_registered_handles_bad_json(self, tmp_path: Path) -> None:
        config = tmp_path / "mcp-config.json"
        config.write_text("NOT JSON", encoding="utf-8")
        assert _is_registered_in_copilot(config) is False


class TestRegisterInCopilot:
    """Tests for ``register_in_copilot()``."""

    def test_register_creates_entry(self, tmp_path: Path) -> None:
        config = tmp_path / "mcp-config.json"
        config.write_text("{}", encoding="utf-8")

        with patch("shutil.which", return_value="/usr/bin/promptc-mcp"):
            ok, msg = register_in_copilot(config)

        assert ok is True
        data = json.loads(config.read_text(encoding="utf-8"))
        assert "promptc" in data["mcpServers"]
        assert data["mcpServers"]["promptc"]["command"] == "/usr/bin/promptc-mcp"

    def test_register_idempotent(self, tmp_path: Path) -> None:
        config = tmp_path / "mcp-config.json"
        config.write_text(
            json.dumps({"mcpServers": {"promptc": {"command": "old"}}}),
            encoding="utf-8",
        )

        with patch("shutil.which", return_value="/usr/bin/promptc-mcp"):
            ok, msg = register_in_copilot(config)

        assert ok is True
        assert "Already registered" in msg
        data = json.loads(config.read_text(encoding="utf-8"))
        assert data["mcpServers"]["promptc"]["command"] == "old"

    def test_register_creates_file_if_missing(self, tmp_path: Path) -> None:
        config = tmp_path / "subdir" / "mcp-config.json"

        with patch("shutil.which", return_value="/usr/bin/promptc-mcp"):
            ok, msg = register_in_copilot(config)

        assert ok is True
        assert config.exists()
        data = json.loads(config.read_text(encoding="utf-8"))
        assert "promptc" in data["mcpServers"]

    def test_register_preserves_existing_servers(self, tmp_path: Path) -> None:
        config = tmp_path / "mcp-config.json"
        config.write_text(
            json.dumps({
                "mcpServers": {"memory": {"command": "memory-server"}},
                "model": "claude-opus-4.6",
            }),
            encoding="utf-8",
        )

        with patch("shutil.which", return_value="/usr/bin/promptc-mcp"):
            ok, msg = register_in_copilot(config)

        assert ok is True
        data = json.loads(config.read_text(encoding="utf-8"))
        assert "memory" in data["mcpServers"]
        assert "promptc" in data["mcpServers"]
        assert data["model"] == "claude-opus-4.6"

    def test_register_fails_without_binary(self, tmp_path: Path) -> None:
        config = tmp_path / "mcp-config.json"
        config.write_text("{}", encoding="utf-8")

        with patch("shutil.which", return_value=None):
            ok, msg = register_in_copilot(config)

        assert ok is False
        assert "not found" in msg.lower()
