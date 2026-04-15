"""PR-14 tests — decision logging foundation."""

from __future__ import annotations

import dataclasses
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from interceptor.observability.decision_log import (
    get_daily_log_path,
    get_log_dir,
    log_decision,
    read_daily_log,
)
from interceptor.observability.models import DecisionRecord


# ── A: DecisionRecord model ──────────────────────────────────────────


class TestDecisionRecordModel:
    def test_defaults(self):
        rec = DecisionRecord()
        assert rec.decision_id
        assert rec.timestamp
        assert rec.outcome == "success"
        assert rec.input_hash == ""

    def test_hash_input_deterministic(self):
        h1 = DecisionRecord.hash_input("hello")
        h2 = DecisionRecord.hash_input("hello")
        assert h1 == h2
        assert len(h1) == 64

    def test_hash_input_different(self):
        h1 = DecisionRecord.hash_input("hello")
        h2 = DecisionRecord.hash_input("world")
        assert h1 != h2

    def test_serialization_keys(self):
        rec = DecisionRecord(input_hash="abc123")
        d = dataclasses.asdict(rec)
        assert "input_hash" in d
        assert "timestamp" in d
        assert "decision_id" in d

    def test_full_record(self):
        rec = DecisionRecord(
            input_hash="abc",
            selected_template="code_review",
            backend="claude",
            finish_reason="stop",
            usage_input_tokens=100,
            usage_output_tokens=200,
            validation_status="pass",
            validation_score=1.0,
            gate_score=0.9,
            gate_hard_passed=True,
            retry_attempts=1,
            retry_outcome="not_needed",
            execution_time_ms=500,
        )
        d = dataclasses.asdict(rec)
        assert d["selected_template"] == "code_review"
        assert d["usage_input_tokens"] == 100
        assert d["gate_score"] == 0.9


# ── B: Privacy contract ──────────────────────────────────────────────


class TestPrivacyContract:
    def test_no_raw_input_field(self):
        fields = {f.name for f in dataclasses.fields(DecisionRecord)}
        assert "raw_input" not in fields
        assert "prompt_text" not in fields
        assert "api_key" not in fields
        assert "response_text" not in fields

    def test_input_hash_is_hex_digest(self):
        h = DecisionRecord.hash_input("test input")
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_not_reversible_to_input(self):
        h = DecisionRecord.hash_input("my secret input")
        assert "my secret input" not in h


# ── C: Log path ──────────────────────────────────────────────────────


class TestLogPath:
    def test_get_log_dir_creates(self, tmp_path):
        d = tmp_path / "logs"
        result = get_log_dir(d)
        assert result == d
        assert d.is_dir()

    def test_daily_filename_format(self, tmp_path):
        p = get_daily_log_path(date(2025, 1, 15), log_dir=tmp_path)
        assert p.name == "decisions-2025-01-15.jsonl"

    def test_daily_path_defaults_to_today(self, tmp_path):
        p = get_daily_log_path(log_dir=tmp_path)
        assert date.today().isoformat() in p.name

    def test_path_has_jsonl_extension(self, tmp_path):
        p = get_daily_log_path(log_dir=tmp_path)
        assert p.suffix == ".jsonl"


# ── D: Append-only JSONL write ───────────────────────────────────────


class TestDecisionLogger:
    def test_append_one_record(self, tmp_path):
        rec = DecisionRecord(input_hash="abc")
        log_decision(rec, log_dir=tmp_path)
        files = list(tmp_path.glob("decisions-*.jsonl"))
        assert len(files) == 1
        lines = files[0].read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["input_hash"] == "abc"

    def test_append_multiple_records(self, tmp_path):
        for i in range(3):
            rec = DecisionRecord(input_hash=f"hash_{i}")
            log_decision(rec, log_dir=tmp_path)
        files = list(tmp_path.glob("decisions-*.jsonl"))
        assert len(files) == 1
        lines = files[0].read_text().strip().split("\n")
        assert len(lines) == 3

    def test_one_json_per_line(self, tmp_path):
        rec = DecisionRecord(input_hash="test")
        log_decision(rec, log_dir=tmp_path)
        files = list(tmp_path.glob("decisions-*.jsonl"))
        text = files[0].read_text()
        for line in text.strip().split("\n"):
            json.loads(line)

    def test_creates_directory_if_missing(self, tmp_path):
        nested = tmp_path / "deep" / "nested"
        rec = DecisionRecord()
        log_decision(rec, log_dir=nested)
        assert nested.is_dir()
        assert len(list(nested.glob("*.jsonl"))) == 1

    def test_json_keys_match_dataclass(self, tmp_path):
        rec = DecisionRecord(input_hash="check_keys")
        log_decision(rec, log_dir=tmp_path)
        files = list(tmp_path.glob("decisions-*.jsonl"))
        data = json.loads(files[0].read_text().strip())
        expected = {f.name for f in dataclasses.fields(DecisionRecord)}
        assert set(data.keys()) == expected


# ── E: Never raises ─────────────────────────────────────────────────


class TestLoggerNeverRaises:
    def test_invalid_path(self):
        rec = DecisionRecord()
        log_decision(rec, log_dir=Path("/proc/nonexistent/impossible"))

    def test_never_raises_on_serialize_quirk(self, tmp_path):
        rec = DecisionRecord(input_hash="ok")
        log_decision(rec, log_dir=tmp_path)


# ── F: Feature flag ──────────────────────────────────────────────────


class TestFeatureFlag:
    def test_config_default_enabled(self):
        from interceptor.config import Config

        cfg = Config()
        assert cfg.observability.decision_logging is True

    def test_config_disabled(self):
        from interceptor.config import Config

        cfg = Config(observability={"decision_logging": False})
        assert cfg.observability.decision_logging is False

    def test_config_from_toml_dict(self):
        from interceptor.config import Config

        cfg = Config.model_validate({
            "observability": {"decision_logging": False}
        })
        assert cfg.observability.decision_logging is False

    def test_log_execution_skips_when_disabled(self, tmp_path, monkeypatch):
        from interceptor.cli import _log_execution

        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path
        )

        class _Obs:
            decision_logging = False

        class _Cfg:
            observability = _Obs()

        _log_execution(_Cfg(), "input", "tpl", "claude", 100)
        assert len(list(tmp_path.glob("*.jsonl"))) == 0

    def test_log_execution_writes_when_enabled(self, tmp_path, monkeypatch):
        from interceptor.cli import _log_execution

        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path
        )

        class _Obs:
            decision_logging = True

        class _Cfg:
            observability = _Obs()

        _log_execution(_Cfg(), "hello", "tpl", "claude", 50)
        records = read_daily_log(log_dir=tmp_path)
        assert len(records) == 1


# ── G: Service integration — success ────────────────────────────────


class TestServiceIntegration:
    def test_success_record_fields(self, tmp_path, monkeypatch):
        from interceptor.cli import _log_execution

        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path
        )

        class _Obs:
            decision_logging = True

        class _Cfg:
            observability = _Obs()

        class _Result:
            backend = "claude"
            finish_reason = "stop"
            usage_input_tokens = 50
            usage_output_tokens = 150
            validation = None
            gate_evaluation = None
            retry_result = None

        _log_execution(
            _Cfg(), "hello world", "code_review", "claude", 200,
            result=_Result(),
        )

        records = read_daily_log(log_dir=tmp_path)
        assert len(records) == 1
        rec = records[0]
        assert rec["input_hash"] == DecisionRecord.hash_input("hello world")
        assert rec["selected_template"] == "code_review"
        assert rec["backend"] == "claude"
        assert rec["finish_reason"] == "stop"
        assert rec["usage_input_tokens"] == 50
        assert rec["usage_output_tokens"] == 150
        assert rec["outcome"] == "success"
        assert rec["execution_time_ms"] == 200

    def test_error_record(self, tmp_path, monkeypatch):
        from interceptor.cli import _log_execution

        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path
        )

        class _Obs:
            decision_logging = True

        class _Cfg:
            observability = _Obs()

        _log_execution(
            _Cfg(), "test", "tpl", "gpt", 100, error="Connection timeout"
        )

        records = read_daily_log(log_dir=tmp_path)
        assert len(records) == 1
        assert records[0]["outcome"] == "error"
        assert records[0]["error"] == "Connection timeout"

    def test_one_record_per_call(self, tmp_path, monkeypatch):
        from interceptor.cli import _log_execution

        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path
        )

        class _Obs:
            decision_logging = True

        class _Cfg:
            observability = _Obs()

        class _Result:
            backend = "gpt"
            finish_reason = "stop"
            usage_input_tokens = 10
            usage_output_tokens = 20
            validation = None
            gate_evaluation = None
            retry_result = None

        for _ in range(5):
            _log_execution(_Cfg(), "x", "t", "gpt", 10, result=_Result())

        records = read_daily_log(log_dir=tmp_path)
        assert len(records) == 5


# ── H: Retry integration ────────────────────────────────────────────


class TestRetryIntegration:
    def test_record_with_retry_recovered(self, tmp_path, monkeypatch):
        from interceptor.cli import _log_execution

        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path
        )

        class _Obs:
            decision_logging = True

        class _Cfg:
            observability = _Obs()

        class _Retry:
            attempts = 2
            outcome = "recovered"

        class _Result:
            backend = "claude"
            finish_reason = "stop"
            usage_input_tokens = 100
            usage_output_tokens = 200
            validation = None
            gate_evaluation = None
            retry_result = _Retry()

        _log_execution(_Cfg(), "test", "tpl", "claude", 500, result=_Result())

        rec = read_daily_log(log_dir=tmp_path)[0]
        assert rec["retry_attempts"] == 2
        assert rec["retry_outcome"] == "recovered"

    def test_record_with_retry_exhausted(self, tmp_path, monkeypatch):
        from interceptor.cli import _log_execution

        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path
        )

        class _Obs:
            decision_logging = True

        class _Cfg:
            observability = _Obs()

        class _Retry:
            attempts = 3
            outcome = "exhausted"

        class _Result:
            backend = "gpt"
            finish_reason = "length"
            usage_input_tokens = 50
            usage_output_tokens = 100
            validation = None
            gate_evaluation = None
            retry_result = _Retry()

        _log_execution(_Cfg(), "x", "tpl", "gpt", 1000, result=_Result())

        rec = read_daily_log(log_dir=tmp_path)[0]
        assert rec["retry_attempts"] == 3
        assert rec["retry_outcome"] == "exhausted"


# ── I: Validation/gate field population ──────────────────────────────


class TestRecordFieldPopulation:
    def test_with_validation(self, tmp_path, monkeypatch):
        from interceptor.cli import _log_execution

        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path
        )

        class _Obs:
            decision_logging = True

        class _Cfg:
            observability = _Obs()

        class _Val:
            status = "fail"
            score = 0.3

        class _Result:
            backend = "claude"
            finish_reason = "stop"
            usage_input_tokens = 10
            usage_output_tokens = 20
            validation = _Val()
            gate_evaluation = None
            retry_result = None

        _log_execution(_Cfg(), "in", "tpl", "claude", 50, result=_Result())

        rec = read_daily_log(log_dir=tmp_path)[0]
        assert rec["validation_status"] == "fail"
        assert rec["validation_score"] == 0.3

    def test_with_gates(self, tmp_path, monkeypatch):
        from interceptor.cli import _log_execution

        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path
        )

        class _Obs:
            decision_logging = True

        class _Cfg:
            observability = _Obs()

        class _Gate:
            gate_score = 0.75
            hard_passed = False

        class _Result:
            backend = "gpt"
            finish_reason = "stop"
            usage_input_tokens = 10
            usage_output_tokens = 20
            validation = None
            gate_evaluation = _Gate()
            retry_result = None

        _log_execution(_Cfg(), "in", "tpl", "gpt", 50, result=_Result())

        rec = read_daily_log(log_dir=tmp_path)[0]
        assert rec["gate_score"] == 0.75
        assert rec["gate_hard_passed"] is False


# ── J: CLI logs command ──────────────────────────────────────────────


class TestCliLogsCommand:
    @staticmethod
    def _write_records(log_dir: Path, count: int) -> None:
        for i in range(count):
            rec = DecisionRecord(
                input_hash=f"hash_{i}",
                selected_template=f"tpl_{i}",
                backend="claude",
                outcome="success",
            )
            log_decision(rec, log_dir=log_dir)

    def test_logs_empty(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from interceptor.cli import app

        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path
        )
        runner = CliRunner()
        result = runner.invoke(app, ["logs"])
        assert result.exit_code == 0

    def test_logs_with_entries(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from interceptor.cli import app

        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path
        )
        self._write_records(tmp_path, 3)

        runner = CliRunner()
        result = runner.invoke(app, ["logs"])
        assert result.exit_code == 0
        assert "3" in result.output

    def test_logs_json(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from interceptor.cli import app

        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path
        )
        self._write_records(tmp_path, 2)

        runner = CliRunner()
        result = runner.invoke(app, ["logs", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total"] == 2
        assert len(data["entries"]) == 2

    def test_logs_count_limit(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from interceptor.cli import app

        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path
        )
        self._write_records(tmp_path, 20)

        runner = CliRunner()
        result = runner.invoke(app, ["logs", "--json", "--count", "5"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total"] == 20
        assert data["showing"] == 5
        assert len(data["entries"]) == 5


# ── K: Read daily log edge cases ─────────────────────────────────────


class TestReadDailyLog:
    def test_missing_file(self, tmp_path):
        records = read_daily_log(log_dir=tmp_path)
        assert records == []

    def test_empty_file(self, tmp_path):
        today = date.today().isoformat()
        (tmp_path / f"decisions-{today}.jsonl").write_text("")
        records = read_daily_log(log_dir=tmp_path)
        assert records == []

    def test_malformed_lines_skipped(self, tmp_path):
        today = date.today().isoformat()
        content = '{"input_hash":"ok"}\nBAD_JSON\n{"input_hash":"also_ok"}\n'
        (tmp_path / f"decisions-{today}.jsonl").write_text(content)
        records = read_daily_log(log_dir=tmp_path)
        assert len(records) == 2
        assert records[0]["input_hash"] == "ok"
        assert records[1]["input_hash"] == "also_ok"


# ── L: Config observability ──────────────────────────────────────────


class TestConfigObservability:
    def test_default_config_has_observability(self):
        from interceptor.config import Config

        cfg = Config()
        assert hasattr(cfg, "observability")
        assert cfg.observability.decision_logging is True

    def test_env_override_disables_logging(self, monkeypatch):
        from interceptor.config import Config, _apply_env_overrides

        monkeypatch.setenv("INTERCEPTOR_DECISION_LOGGING", "false")
        data = Config().model_dump()
        data = _apply_env_overrides(data)
        assert data["observability"]["decision_logging"] is False

    def test_env_override_enables_logging(self, monkeypatch):
        from interceptor.config import _apply_env_overrides

        monkeypatch.setenv("INTERCEPTOR_DECISION_LOGGING", "true")
        data = {"observability": {"decision_logging": False}}
        data = _apply_env_overrides(data)
        assert data["observability"]["decision_logging"] is True


# ── M: Regression safety ─────────────────────────────────────────────


class TestRegression:
    def test_execution_result_unchanged(self):
        from interceptor.adapters.models import ExecutionResult

        result = ExecutionResult(backend="claude", text="hello")
        assert result.retry_result is None
        assert result.validation is None
        assert result.gate_evaluation is None

    def test_config_backwards_compatible(self):
        from interceptor.config import Config

        cfg = Config()
        assert hasattr(cfg, "general")
        assert hasattr(cfg, "routing")
        assert hasattr(cfg, "backends")
        assert hasattr(cfg, "plugins")
        assert hasattr(cfg, "observability")

    def test_constants_log_dir(self):
        from interceptor.constants import DATA_DIR, LOG_DIR

        assert LOG_DIR == DATA_DIR / "logs"
