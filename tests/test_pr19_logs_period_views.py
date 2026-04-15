"""PR-19 tests — period-based decision log views (today/week/month)."""

from __future__ import annotations

import gzip
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from interceptor.cli import app
from interceptor.observability.log_search import search_logs

runner = CliRunner()

_NOW = datetime(2025, 7, 15, 12, 0, 0, tzinfo=timezone.utc)


def _rec(
    ts: str,
    template: str = "code-review",
    **kw: object,
) -> dict:
    return {
        "timestamp": ts,
        "decision_id": "test-id",
        "selected_template": template,
        "backend": "gpt-4",
        "outcome": "success",
        "execution_time_ms": 100,
        **kw,
    }


def _write(
    d: Path, date_str: str, records: list[dict], *, gz: bool = False
) -> Path:
    lines = "\n".join(json.dumps(r) for r in records) + "\n"
    if gz:
        p = d / f"decisions-{date_str}.jsonl.gz"
        p.write_bytes(gzip.compress(lines.encode("utf-8")))
    else:
        p = d / f"decisions-{date_str}.jsonl"
        p.write_text(lines, encoding="utf-8")
    return p


# ── A: logs today returns only records within 24h ───────────────


class TestA_TodayWindow:
    def test_within_24h(self, tmp_path: Path):
        _write(tmp_path, "2025-07-15", [_rec("2025-07-15T10:00:00+00:00")])
        _write(tmp_path, "2025-07-10", [_rec("2025-07-10T10:00:00+00:00")])
        results = search_logs(tmp_path, since=timedelta(days=1), now=_NOW)
        assert len(results) == 1
        assert "07-15" in results[0]["timestamp"]


# ── B: logs week returns only records within 7d ─────────────────


class TestB_WeekWindow:
    def test_within_7d(self, tmp_path: Path):
        _write(tmp_path, "2025-07-14", [_rec("2025-07-14T20:00:00+00:00")])
        _write(tmp_path, "2025-07-01", [_rec("2025-07-01T10:00:00+00:00")])
        results = search_logs(tmp_path, since=timedelta(days=7), now=_NOW)
        assert len(results) == 1
        assert "07-14" in results[0]["timestamp"]


# ── C: logs month returns only records within 30d ───────────────


class TestC_MonthWindow:
    def test_within_30d(self, tmp_path: Path):
        _write(tmp_path, "2025-07-10", [_rec("2025-07-10T10:00:00+00:00")])
        _write(tmp_path, "2025-05-01", [_rec("2025-05-01T10:00:00+00:00")])
        results = search_logs(tmp_path, since=timedelta(days=30), now=_NOW)
        assert len(results) == 1
        assert "07-10" in results[0]["timestamp"]


# ── D: template filter on today ─────────────────────────────────


class TestD_TodayTemplate:
    def test_filter(self, tmp_path: Path):
        _write(tmp_path, "2025-07-15", [
            _rec("2025-07-15T11:00:00+00:00", template="code-review"),
            _rec("2025-07-15T11:30:00+00:00", template="summarize"),
        ])
        results = search_logs(
            tmp_path, template="code-review", since=timedelta(days=1), now=_NOW,
        )
        assert len(results) == 1
        assert results[0]["selected_template"] == "code-review"


# ── E: template filter on week ──────────────────────────────────


class TestE_WeekTemplate:
    def test_filter(self, tmp_path: Path):
        _write(tmp_path, "2025-07-12", [
            _rec("2025-07-12T10:00:00+00:00", template="code-review"),
            _rec("2025-07-12T11:00:00+00:00", template="summarize"),
        ])
        results = search_logs(
            tmp_path, template="summarize", since=timedelta(days=7), now=_NOW,
        )
        assert len(results) == 1
        assert results[0]["selected_template"] == "summarize"


# ── F: template filter on month ─────────────────────────────────


class TestF_MonthTemplate:
    def test_filter(self, tmp_path: Path):
        _write(tmp_path, "2025-07-05", [
            _rec("2025-07-05T10:00:00+00:00", template="code-review"),
            _rec("2025-07-05T11:00:00+00:00", template="fix-bug"),
        ])
        results = search_logs(
            tmp_path, template="fix-bug", since=timedelta(days=30), now=_NOW,
        )
        assert len(results) == 1
        assert results[0]["selected_template"] == "fix-bug"


# ── G: newest-first ordering preserved ──────────────────────────


class TestG_NewestFirst:
    def test_ordering(self, tmp_path: Path):
        _write(tmp_path, "2025-07-15", [_rec("2025-07-15T08:00:00+00:00")])
        _write(tmp_path, "2025-07-14", [_rec("2025-07-14T20:00:00+00:00")])
        results = search_logs(tmp_path, since=timedelta(days=7), now=_NOW)
        assert len(results) == 2
        ts = [r["timestamp"] for r in results]
        assert ts == sorted(ts, reverse=True)


# ── H: limit applied after filtering ────────────────────────────


class TestH_LimitAfterFilter:
    def test_limit(self, tmp_path: Path):
        _write(tmp_path, "2025-07-15", [
            _rec(f"2025-07-15T{h:02d}:00:00+00:00") for h in range(10)
        ])
        results = search_logs(
            tmp_path, since=timedelta(days=1), now=_NOW, limit=3,
        )
        assert len(results) == 3
        assert results[0]["timestamp"] > results[2]["timestamp"]


# ── I: zero-result human output ─────────────────────────────────


class TestI_ZeroHuman:
    def test_today_empty(self, tmp_path: Path):
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(app, ["logs", "today"])
        assert result.exit_code == 0
        assert "No matching records" in result.output

    def test_week_empty(self, tmp_path: Path):
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(app, ["logs", "week"])
        assert result.exit_code == 0
        assert "No matching records" in result.output

    def test_month_empty(self, tmp_path: Path):
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(app, ["logs", "month"])
        assert result.exit_code == 0
        assert "No matching records" in result.output


# ── J: zero-result JSON output ──────────────────────────────────


class TestJ_ZeroJson:
    def test_today_json(self, tmp_path: Path):
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(app, ["logs", "today", "--json"])
        assert result.exit_code == 0
        assert json.loads(result.output) == []

    def test_week_json(self, tmp_path: Path):
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(app, ["logs", "week", "--json"])
        assert result.exit_code == 0
        assert json.loads(result.output) == []

    def test_month_json(self, tmp_path: Path):
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(app, ["logs", "month", "--json"])
        assert result.exit_code == 0
        assert json.loads(result.output) == []


# ── K: .jsonl.gz records included ───────────────────────────────


class TestK_GzIncluded:
    def test_gz_in_week(self, tmp_path: Path):
        _write(
            tmp_path, "2025-07-12",
            [_rec("2025-07-12T10:00:00+00:00")], gz=True,
        )
        results = search_logs(tmp_path, since=timedelta(days=7), now=_NOW)
        assert len(results) == 1


# ── L: mixed .jsonl + .jsonl.gz ─────────────────────────────────


class TestL_MixedFiles:
    def test_mixed(self, tmp_path: Path):
        _write(tmp_path, "2025-07-14", [_rec("2025-07-14T20:00:00+00:00")])
        _write(
            tmp_path, "2025-07-12",
            [_rec("2025-07-12T10:00:00+00:00")], gz=True,
        )
        results = search_logs(tmp_path, since=timedelta(days=7), now=_NOW)
        assert len(results) == 2


# ── M: missing dir safe ────────────────────────────────────────


class TestM_MissingDir:
    def test_missing(self, tmp_path: Path):
        results = search_logs(
            tmp_path / "nope", since=timedelta(days=1), now=_NOW,
        )
        assert results == []


# ── N: malformed/corrupt records do not abort ───────────────────


class TestN_MalformedSafe:
    def test_corrupt_gz_skipped(self, tmp_path: Path):
        (tmp_path / "decisions-2025-07-15.jsonl.gz").write_bytes(b"bad")
        _write(tmp_path, "2025-07-15", [_rec("2025-07-15T11:00:00+00:00")])
        results = search_logs(tmp_path, since=timedelta(days=1), now=_NOW)
        assert len(results) == 1

    def test_bad_json_skipped(self, tmp_path: Path):
        p = tmp_path / "decisions-2025-07-15.jsonl"
        p.write_text(
            json.dumps(_rec("2025-07-15T11:00:00+00:00"))
            + "\nnot json\n",
            encoding="utf-8",
        )
        results = search_logs(tmp_path, since=timedelta(days=1), now=_NOW)
        assert len(results) == 1


# ── O: CLI logs today --json ────────────────────────────────────


class TestO_CliTodayJson:
    def test_today_json(self, tmp_path: Path):
        now = datetime.now(timezone.utc)
        recent = now - timedelta(hours=1)
        _write(
            tmp_path, recent.strftime("%Y-%m-%d"),
            [_rec(recent.isoformat())],
        )
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(app, ["logs", "today", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1


# ── P: CLI logs week --json ─────────────────────────────────────


class TestP_CliWeekJson:
    def test_week_json(self, tmp_path: Path):
        now = datetime.now(timezone.utc)
        recent = now - timedelta(days=2)
        old = now - timedelta(days=30)
        _write(
            tmp_path, recent.strftime("%Y-%m-%d"),
            [_rec(recent.isoformat())],
        )
        _write(
            tmp_path, old.strftime("%Y-%m-%d"),
            [_rec(old.isoformat())],
        )
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(app, ["logs", "week", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1


# ── Q: CLI logs month --json ────────────────────────────────────


class TestQ_CliMonthJson:
    def test_month_json(self, tmp_path: Path):
        now = datetime.now(timezone.utc)
        recent = now - timedelta(days=10)
        old = now - timedelta(days=60)
        _write(
            tmp_path, recent.strftime("%Y-%m-%d"),
            [_rec(recent.isoformat())],
        )
        _write(
            tmp_path, old.strftime("%Y-%m-%d"),
            [_rec(old.isoformat())],
        )
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(app, ["logs", "month", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1


# ── R: regression safety ────────────────────────────────────────


class TestR_Regression:
    def test_logs_callback(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path,
        )
        result = runner.invoke(app, ["logs"])
        assert result.exit_code == 0

    def test_logs_search(self, tmp_path: Path):
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(app, ["logs", "search"])
        assert result.exit_code == 0

    def test_logs_prune(self, tmp_path: Path):
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(
                app, ["logs", "prune", "--before", "2025-01-01"],
            )
        assert result.exit_code == 0

    def test_logs_rotate(self, tmp_path: Path):
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(app, ["logs", "rotate"])
        assert result.exit_code == 0

    def test_stats(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path,
        )
        result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0
