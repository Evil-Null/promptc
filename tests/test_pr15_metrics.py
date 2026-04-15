"""PR-15 tests — derived metrics foundation."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from interceptor.observability.decision_log import log_decision, read_daily_log
from interceptor.observability.metrics import StatsSnapshot, TemplateUsage, aggregate
from interceptor.observability.models import DecisionRecord


def _rec(**overrides: object) -> dict:
    """Build a minimal decision-log dict with sensible defaults."""
    base: dict = {
        "timestamp": "2025-01-15T10:00:00+00:00",
        "decision_id": "aaa",
        "input_hash": "abc123",
        "selected_template": "code_review",
        "backend": "claude",
        "finish_reason": "stop",
        "usage_input_tokens": 100,
        "usage_output_tokens": 200,
        "validation_status": None,
        "validation_score": None,
        "gate_score": None,
        "gate_hard_passed": None,
        "retry_attempts": None,
        "retry_outcome": None,
        "outcome": "success",
        "execution_time_ms": 500,
        "error": None,
    }
    base.update(overrides)
    return base


# ── A: Empty log set ─────────────────────────────────────────────────


class TestEmptyLogSet:
    def test_zero_snapshot(self):
        snap = aggregate([])
        assert snap.total_decisions == 0
        assert snap.success_count == 0
        assert snap.error_count == 0
        assert snap.average_execution_time_ms is None
        assert snap.retry_rate is None
        assert snap.average_gate_score is None
        assert snap.average_validation_score is None
        assert snap.top_templates == []

    def test_snapshot_default(self):
        snap = StatsSnapshot()
        assert snap.total_decisions == 0
        assert snap.top_templates == []


# ── B: Single record aggregation ─────────────────────────────────────


class TestSingleRecord:
    def test_one_success(self):
        snap = aggregate([_rec()])
        assert snap.total_decisions == 1
        assert snap.success_count == 1
        assert snap.error_count == 0
        assert snap.average_execution_time_ms == 500.0

    def test_one_error(self):
        snap = aggregate([_rec(outcome="error", error="timeout")])
        assert snap.total_decisions == 1
        assert snap.success_count == 0
        assert snap.error_count == 1

    def test_single_template_top(self):
        snap = aggregate([_rec(selected_template="debug")])
        assert len(snap.top_templates) == 1
        assert snap.top_templates[0].name == "debug"
        assert snap.top_templates[0].count == 1


# ── C: Multi-record averages ─────────────────────────────────────────


class TestMultiRecordAverages:
    def test_average_execution_time(self):
        records = [
            _rec(execution_time_ms=100),
            _rec(execution_time_ms=300),
            _rec(execution_time_ms=500),
        ]
        snap = aggregate(records)
        assert snap.average_execution_time_ms == 300.0

    def test_average_gate_score(self):
        records = [
            _rec(gate_score=0.6),
            _rec(gate_score=0.8),
        ]
        snap = aggregate(records)
        assert snap.average_gate_score == 0.7

    def test_average_validation_score(self):
        records = [
            _rec(validation_score=0.5),
            _rec(validation_score=1.0),
        ]
        snap = aggregate(records)
        assert snap.average_validation_score == 0.75

    def test_mixed_outcomes(self):
        records = [
            _rec(outcome="success"),
            _rec(outcome="success"),
            _rec(outcome="error", error="fail"),
        ]
        snap = aggregate(records)
        assert snap.success_count == 2
        assert snap.error_count == 1


# ── D: Retry rate ────────────────────────────────────────────────────


class TestRetryRate:
    def test_no_retries(self):
        records = [_rec(), _rec()]
        snap = aggregate(records)
        assert snap.retry_rate == 0.0

    def test_all_retried(self):
        records = [
            _rec(retry_attempts=2),
            _rec(retry_attempts=1),
        ]
        snap = aggregate(records)
        assert snap.retry_rate == 1.0

    def test_partial_retries(self):
        records = [
            _rec(retry_attempts=None),
            _rec(retry_attempts=0),
            _rec(retry_attempts=2),
            _rec(retry_attempts=1),
        ]
        snap = aggregate(records)
        assert snap.retry_rate == 0.5


# ── E: Schema compliance with missing values ─────────────────────────


class TestSchemaCompliance:
    def test_all_present(self):
        records = [
            _rec(validation_score=0.8),
            _rec(validation_score=1.0),
        ]
        snap = aggregate(records)
        assert snap.average_validation_score == 0.9

    def test_some_missing(self):
        records = [
            _rec(validation_score=0.6),
            _rec(validation_score=None),
            _rec(validation_score=1.0),
        ]
        snap = aggregate(records)
        assert snap.average_validation_score == 0.8

    def test_all_missing(self):
        records = [_rec(validation_score=None), _rec(validation_score=None)]
        snap = aggregate(records)
        assert snap.average_validation_score is None


# ── F: Gate score with missing values ────────────────────────────────


class TestGateScore:
    def test_all_present(self):
        records = [
            _rec(gate_score=0.7),
            _rec(gate_score=0.9),
        ]
        snap = aggregate(records)
        assert snap.average_gate_score == 0.8

    def test_some_missing(self):
        records = [
            _rec(gate_score=0.5),
            _rec(gate_score=None),
            _rec(gate_score=0.7),
        ]
        snap = aggregate(records)
        assert snap.average_gate_score == 0.6

    def test_all_missing(self):
        records = [_rec(gate_score=None)]
        snap = aggregate(records)
        assert snap.average_gate_score is None


# ── G: Malformed log lines ───────────────────────────────────────────


class TestMalformedRecords:
    def test_non_dict_skipped(self):
        records = [_rec(), "bad", 42, None, _rec()]  # type: ignore[list-item]
        snap = aggregate(records)
        assert snap.total_decisions == 2
        assert snap.success_count == 2

    def test_missing_outcome_field(self):
        rec = _rec()
        del rec["outcome"]
        snap = aggregate([rec])
        assert snap.total_decisions == 1
        assert snap.success_count == 0
        assert snap.error_count == 0

    def test_non_numeric_execution_time(self):
        snap = aggregate([_rec(execution_time_ms="slow")])
        assert snap.average_execution_time_ms is None


# ── H: Top template ranking ─────────────────────────────────────────


class TestTopTemplates:
    def test_ranking_order(self):
        records = [
            _rec(selected_template="debug"),
            _rec(selected_template="code_review"),
            _rec(selected_template="code_review"),
            _rec(selected_template="code_review"),
            _rec(selected_template="debug"),
        ]
        snap = aggregate(records)
        assert len(snap.top_templates) == 2
        assert snap.top_templates[0].name == "code_review"
        assert snap.top_templates[0].count == 3
        assert snap.top_templates[1].name == "debug"
        assert snap.top_templates[1].count == 2

    def test_top_n_limit(self):
        records = [_rec(selected_template=f"tpl_{i}") for i in range(10)]
        snap = aggregate(records, top_n=3)
        assert len(snap.top_templates) == 3

    def test_empty_template_excluded(self):
        records = [_rec(selected_template=""), _rec(selected_template="debug")]
        snap = aggregate(records)
        assert len(snap.top_templates) == 1
        assert snap.top_templates[0].name == "debug"


# ── I: CLI stats human output ────────────────────────────────────────


class TestCliStatsHuman:
    @staticmethod
    def _write(log_dir: Path, count: int) -> None:
        for i in range(count):
            rec = DecisionRecord(
                input_hash=f"h{i}",
                selected_template="code_review",
                backend="claude",
                outcome="success",
                execution_time_ms=200 + i * 100,
                gate_score=0.8,
                validation_score=0.9,
            )
            log_decision(rec, log_dir=log_dir)

    def test_stats_empty(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from interceptor.cli import app

        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path
        )
        runner = CliRunner()
        result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0
        assert "No decisions" in result.output

    def test_stats_with_data(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from interceptor.cli import app

        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path
        )
        self._write(tmp_path, 3)

        runner = CliRunner()
        result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0
        assert "Decisions" in result.output
        assert "3" in result.output

    def test_stats_shows_metrics(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from interceptor.cli import app

        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path
        )
        self._write(tmp_path, 2)

        runner = CliRunner()
        result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0
        assert "Avg time" in result.output
        assert "Avg gate" in result.output


# ── J: CLI stats JSON output ─────────────────────────────────────────


class TestCliStatsJson:
    @staticmethod
    def _write(log_dir: Path, count: int) -> None:
        for i in range(count):
            rec = DecisionRecord(
                input_hash=f"h{i}",
                selected_template="debug" if i % 2 == 0 else "code_review",
                backend="claude",
                outcome="success",
                execution_time_ms=100,
                retry_attempts=1 if i == 0 else None,
            )
            log_decision(rec, log_dir=log_dir)

    def test_json_empty(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from interceptor.cli import app

        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path
        )
        runner = CliRunner()
        result = runner.invoke(app, ["stats", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total_decisions"] == 0

    def test_json_with_data(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from interceptor.cli import app

        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path
        )
        self._write(tmp_path, 4)

        runner = CliRunner()
        result = runner.invoke(app, ["stats", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total_decisions"] == 4
        assert data["success_count"] == 4
        assert data["average_execution_time_ms"] == 100.0
        assert data["retry_rate"] == 0.25
        assert len(data["top_templates"]) == 2

    def test_json_date_flag(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from interceptor.cli import app

        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path
        )
        runner = CliRunner()
        result = runner.invoke(app, ["stats", "--json", "--date", "2025-03-01"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["date"] == "2025-03-01"
        assert data["total_decisions"] == 0

    def test_json_invalid_date(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from interceptor.cli import app

        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path
        )
        runner = CliRunner()
        result = runner.invoke(app, ["stats", "--date", "not-a-date"])
        assert result.exit_code == 1


# ── K: Missing log file ─────────────────────────────────────────────


class TestMissingLogFile:
    def test_aggregate_from_missing(self, tmp_path):
        records = read_daily_log(log_dir=tmp_path)
        snap = aggregate(records)
        assert snap.total_decisions == 0

    def test_stats_missing_file_no_crash(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from interceptor.cli import app

        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path
        )
        runner = CliRunner()
        result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0


# ── L: Regression — PR-14 log format assumptions ────────────────────


class TestRegression:
    def test_written_records_aggregatable(self, tmp_path):
        rec = DecisionRecord(
            input_hash="abc",
            selected_template="code_review",
            backend="claude",
            finish_reason="stop",
            usage_input_tokens=100,
            usage_output_tokens=200,
            gate_score=0.85,
            validation_score=0.9,
            retry_attempts=1,
            execution_time_ms=300,
        )
        log_decision(rec, log_dir=tmp_path)
        records = read_daily_log(log_dir=tmp_path)
        snap = aggregate(records)
        assert snap.total_decisions == 1
        assert snap.average_execution_time_ms == 300.0
        assert snap.average_gate_score == 0.85
        assert snap.average_validation_score == 0.9
        assert snap.retry_rate == 1.0

    def test_pr14_log_command_still_works(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from interceptor.cli import app

        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path
        )
        runner = CliRunner()
        result = runner.invoke(app, ["logs"])
        assert result.exit_code == 0

    def test_decision_record_unchanged(self):
        import dataclasses

        fields = {f.name for f in dataclasses.fields(DecisionRecord)}
        assert "input_hash" in fields
        assert "gate_score" in fields
        assert "retry_attempts" in fields
        assert "execution_time_ms" in fields

    def test_template_usage_model(self):
        t = TemplateUsage(name="test", count=5)
        assert t.name == "test"
        assert t.count == 5
