"""Tests for full-text decision log search."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def _write_log(tmp_path: Path, records: list[dict]) -> Path:
    """Write records as a canonical JSONL log file."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    path = log_dir / "decisions-2025-07-16.jsonl"
    lines = [json.dumps(r, ensure_ascii=False) for r in records]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return log_dir


SAMPLE_RECORDS = [
    {
        "timestamp": "2025-07-16T10:00:00+00:00",
        "raw_input": "Review my Python authentication code",
        "selected_template": "code-review",
        "route_reason": "keyword match",
    },
    {
        "timestamp": "2025-07-16T11:00:00+00:00",
        "raw_input": "Explain how Docker networking works",
        "selected_template": "explain",
        "route_reason": "fuzzy match",
    },
    {
        "timestamp": "2025-07-16T12:00:00+00:00",
        "raw_input": "Design a microservice architecture",
        "selected_template": "architecture",
        "route_reason": "keyword match",
    },
]


class TestFullTextSearch:
    def test_query_matches_raw_input(self, tmp_path: Path) -> None:
        from interceptor.observability.log_search import search_logs

        log_dir = _write_log(tmp_path, SAMPLE_RECORDS)
        results = search_logs(log_dir, query="Python authentication")
        assert len(results) == 1
        assert results[0]["selected_template"] == "code-review"

    def test_query_matches_template(self, tmp_path: Path) -> None:
        from interceptor.observability.log_search import search_logs

        log_dir = _write_log(tmp_path, SAMPLE_RECORDS)
        results = search_logs(log_dir, query="architecture")
        assert len(results) == 1
        assert results[0]["selected_template"] == "architecture"

    def test_query_case_insensitive(self, tmp_path: Path) -> None:
        from interceptor.observability.log_search import search_logs

        log_dir = _write_log(tmp_path, SAMPLE_RECORDS)
        results = search_logs(log_dir, query="DOCKER")
        assert len(results) == 1
        assert results[0]["selected_template"] == "explain"

    def test_query_no_match(self, tmp_path: Path) -> None:
        from interceptor.observability.log_search import search_logs

        log_dir = _write_log(tmp_path, SAMPLE_RECORDS)
        results = search_logs(log_dir, query="nonexistent_xyz_term")
        assert len(results) == 0

    def test_query_combined_with_template_filter(self, tmp_path: Path) -> None:
        from interceptor.observability.log_search import search_logs

        log_dir = _write_log(tmp_path, SAMPLE_RECORDS)
        # "keyword" appears in two records' route_reason, but only one is code-review
        results = search_logs(log_dir, query="keyword", template="code-review")
        assert len(results) == 1

    def test_query_with_limit(self, tmp_path: Path) -> None:
        from interceptor.observability.log_search import search_logs

        log_dir = _write_log(tmp_path, SAMPLE_RECORDS)
        results = search_logs(log_dir, query="match", limit=1)
        assert len(results) == 1

    def test_query_none_returns_all(self, tmp_path: Path) -> None:
        from interceptor.observability.log_search import search_logs

        log_dir = _write_log(tmp_path, SAMPLE_RECORDS)
        results = search_logs(log_dir, query=None)
        assert len(results) == 3

    def test_empty_query_returns_all(self, tmp_path: Path) -> None:
        from interceptor.observability.log_search import search_logs

        log_dir = _write_log(tmp_path, SAMPLE_RECORDS)
        results = search_logs(log_dir, query="")
        assert len(results) == 3


class TestCliSearchQuery:
    """Test the CLI --query option via CliRunner."""

    def test_search_with_query_flag(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from typer.testing import CliRunner

        from interceptor import constants
        from interceptor.cli import app

        log_dir = _write_log(tmp_path, SAMPLE_RECORDS)
        monkeypatch.setattr(constants, "LOG_DIR", log_dir)

        runner = CliRunner()
        result = runner.invoke(app, ["logs", "search", "--query", "Docker"])
        assert result.exit_code == 0
        assert "explain" in result.output

    def test_search_with_q_shorthand(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from typer.testing import CliRunner

        from interceptor import constants
        from interceptor.cli import app

        log_dir = _write_log(tmp_path, SAMPLE_RECORDS)
        monkeypatch.setattr(constants, "LOG_DIR", log_dir)

        runner = CliRunner()
        result = runner.invoke(app, ["logs", "search", "-q", "Docker"])
        assert result.exit_code == 0
        assert "explain" in result.output
