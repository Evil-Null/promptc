"""Tests for the backend CLI sub-commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from interceptor.cli import app

runner = CliRunner()


class TestBackendList:
    def test_list_shows_backends(self) -> None:
        result = runner.invoke(app, ["backend", "list"])
        assert result.exit_code == 0
        assert "claude" in result.output
        assert "gpt" in result.output

    def test_list_json(self) -> None:
        result = runner.invoke(app, ["backend", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 2
        names = {d["name"] for d in data}
        assert names == {"claude", "gpt"}


class TestBackendInspect:
    def test_inspect_claude(self) -> None:
        result = runner.invoke(app, ["backend", "inspect", "claude"])
        assert result.exit_code == 0
        assert "claude" in result.output

    def test_inspect_gpt_json(self) -> None:
        result = runner.invoke(app, ["backend", "inspect", "gpt", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["name"] == "gpt"
        assert data["max_tokens"] == 128_000
        assert data["supports_structured_output"] is True

    def test_inspect_unknown_exits_1(self) -> None:
        result = runner.invoke(app, ["backend", "inspect", "llama"])
        assert result.exit_code == 1
        assert "Error" in result.output


class TestHealthIntegration:
    def test_health_includes_backends(self) -> None:
        result = runner.invoke(app, ["health"])
        assert result.exit_code == 0
        assert "backends_valid" in result.output

    def test_health_check_backends_only(self) -> None:
        result = runner.invoke(app, ["health", "--check", "backends_valid"])
        assert result.exit_code == 0
        assert "backends_valid" in result.output
