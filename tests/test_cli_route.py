"""Tests for `mycli route` CLI command."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from interceptor.cli import app

runner = CliRunner()


class TestRouteBasic:
    def test_route_review_code(self) -> None:
        result = runner.invoke(app, ["route", "review this code"])
        assert result.exit_code == 0
        assert "code-review" in result.output

    def test_route_passthrough(self) -> None:
        result = runner.invoke(app, ["route", "send an email"])
        assert result.exit_code == 0
        assert "No template matched" in result.output

    def test_route_json_output(self) -> None:
        result = runner.invoke(app, ["route", "--json", "review this code"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["template_name"] == "code-review"
        assert "zone" in data

    def test_route_json_passthrough(self) -> None:
        result = runner.invoke(app, ["route", "--json", "send an email"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["zone"] == "PASSTHROUGH"


class TestRouteExplicit:
    def test_explicit_template(self) -> None:
        result = runner.invoke(app, ["route", "--template", "code-review", "anything"])
        assert result.exit_code == 0
        assert "code-review" in result.output

    def test_explicit_unknown(self) -> None:
        result = runner.invoke(app, ["route", "--template", "zzzzzzzzz", "anything"])
        assert result.exit_code == 0
        assert "Error" in result.output


class TestRouteFileContext:
    def test_file_option(self) -> None:
        result = runner.invoke(app, ["route", "--file", "app.py", "some random text"])
        assert result.exit_code == 0

    def test_file_yaml(self) -> None:
        result = runner.invoke(app, ["route", "--file", "config.yaml", "random input"])
        assert result.exit_code == 0


class TestRouteScoresDisplay:
    def test_scores_shown(self) -> None:
        result = runner.invoke(app, ["route", "review this code"])
        assert result.exit_code == 0
        assert "█" in result.output or "░" in result.output

    def test_dry_run_note(self) -> None:
        result = runner.invoke(app, ["route", "review this code"])
        assert result.exit_code == 0
        assert "dry-run" in result.output.lower()
