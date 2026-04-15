"""PR-18 tests — decision log search."""

from __future__ import annotations

import gzip
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from interceptor.cli import app
from interceptor.observability.log_search import parse_since, search_logs

runner = CliRunner()

_NOW = datetime(2025, 7, 1, 12, 0, 0, tzinfo=timezone.utc)


def _rec(
    ts: str,
    template: str = "code-review",
    backend: str = "gpt-4",
    outcome: str = "success",
    **kw: object,
) -> dict:
    return {
        "timestamp": ts,
        "decision_id": "abc123",
        "selected_template": template,
        "backend": backend,
        "outcome": outcome,
        "execution_time_ms": 150,
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


# ── A: Search canonical .jsonl records ──────────────────────────


class TestA_SearchJsonl:
    def test_reads_single(self, tmp_path: Path):
        _write(tmp_path, "2025-06-30", [_rec("2025-06-30T10:00:00+00:00")])
        results = search_logs(tmp_path)
        assert len(results) == 1
        assert results[0]["selected_template"] == "code-review"

    def test_reads_multiple_lines(self, tmp_path: Path):
        _write(
            tmp_path,
            "2025-06-30",
            [
                _rec("2025-06-30T10:00:00+00:00"),
                _rec("2025-06-30T11:00:00+00:00"),
            ],
        )
        results = search_logs(tmp_path)
        assert len(results) == 2


# ── B: Search canonical .jsonl.gz records ───────────────────────


class TestB_SearchGz:
    def test_reads_gz(self, tmp_path: Path):
        _write(
            tmp_path, "2025-06-20", [_rec("2025-06-20T10:00:00+00:00")], gz=True
        )
        results = search_logs(tmp_path)
        assert len(results) == 1

    def test_reads_gz_multiple(self, tmp_path: Path):
        _write(
            tmp_path,
            "2025-06-20",
            [
                _rec("2025-06-20T10:00:00+00:00"),
                _rec("2025-06-20T11:00:00+00:00"),
            ],
            gz=True,
        )
        results = search_logs(tmp_path)
        assert len(results) == 2


# ── C: Mixed .jsonl + .jsonl.gz inputs ──────────────────────────


class TestC_Mixed:
    def test_reads_both(self, tmp_path: Path):
        _write(tmp_path, "2025-06-30", [_rec("2025-06-30T10:00:00+00:00")])
        _write(
            tmp_path, "2025-06-20", [_rec("2025-06-20T10:00:00+00:00")], gz=True
        )
        results = search_logs(tmp_path)
        assert len(results) == 2


# ── D: Unrelated files ignored ──────────────────────────────────


class TestD_Unrelated:
    def test_random_file(self, tmp_path: Path):
        (tmp_path / "random.txt").write_text("hello")
        _write(tmp_path, "2025-06-30", [_rec("2025-06-30T10:00:00+00:00")])
        assert len(search_logs(tmp_path)) == 1

    def test_bad_date_ignored(self, tmp_path: Path):
        (tmp_path / "decisions-bad.jsonl").write_text('{"timestamp":"x"}\n')
        _write(tmp_path, "2025-06-30", [_rec("2025-06-30T10:00:00+00:00")])
        assert len(search_logs(tmp_path)) == 1


# ── E: Missing dir → empty ──────────────────────────────────────


class TestE_MissingDir:
    def test_missing_dir(self, tmp_path: Path):
        assert search_logs(tmp_path / "nope") == []


# ── F: Template filter match ────────────────────────────────────


class TestF_TemplateMatch:
    def test_matches(self, tmp_path: Path):
        _write(
            tmp_path,
            "2025-06-30",
            [
                _rec("2025-06-30T10:00:00+00:00", template="code-review"),
                _rec("2025-06-30T11:00:00+00:00", template="summarize"),
            ],
        )
        results = search_logs(tmp_path, template="code-review")
        assert len(results) == 1
        assert results[0]["selected_template"] == "code-review"

    def test_exact_match_only(self, tmp_path: Path):
        _write(
            tmp_path,
            "2025-06-30",
            [_rec("2025-06-30T10:00:00+00:00", template="code-review-v2")],
        )
        assert search_logs(tmp_path, template="code-review") == []


# ── G: Template filter no match ─────────────────────────────────


class TestG_TemplateNoMatch:
    def test_no_match(self, tmp_path: Path):
        _write(
            tmp_path,
            "2025-06-30",
            [_rec("2025-06-30T10:00:00+00:00", template="code-review")],
        )
        assert search_logs(tmp_path, template="nonexistent") == []


# ── H: Since filter with hours ──────────────────────────────────


class TestH_SinceHours:
    def test_within_hours(self, tmp_path: Path):
        _write(
            tmp_path,
            "2025-07-01",
            [
                _rec("2025-07-01T11:30:00+00:00"),
                _rec("2025-07-01T08:00:00+00:00"),
            ],
        )
        results = search_logs(tmp_path, since=timedelta(hours=1), now=_NOW)
        assert len(results) == 1
        assert results[0]["timestamp"] == "2025-07-01T11:30:00+00:00"


# ── I: Since filter with days ───────────────────────────────────


class TestI_SinceDays:
    def test_within_days(self, tmp_path: Path):
        _write(tmp_path, "2025-07-01", [_rec("2025-07-01T10:00:00+00:00")])
        _write(tmp_path, "2025-06-20", [_rec("2025-06-20T10:00:00+00:00")])
        results = search_logs(tmp_path, since=timedelta(days=3), now=_NOW)
        assert len(results) == 1
        assert "07-01" in results[0]["timestamp"]


# ── J: Since boundary behaviour ─────────────────────────────────


class TestJ_SinceBoundary:
    def test_exact_boundary_included(self, tmp_path: Path):
        _write(
            tmp_path,
            "2025-07-01",
            [_rec("2025-07-01T11:00:00+00:00")],
        )
        results = search_logs(tmp_path, since=timedelta(hours=1), now=_NOW)
        assert len(results) == 1

    def test_just_outside_excluded(self, tmp_path: Path):
        _write(
            tmp_path,
            "2025-07-01",
            [_rec("2025-07-01T10:59:59+00:00")],
        )
        results = search_logs(tmp_path, since=timedelta(hours=1), now=_NOW)
        assert len(results) == 0


# ── K: Malformed JSON line skipped ──────────────────────────────


class TestK_MalformedJson:
    def test_bad_json_skipped(self, tmp_path: Path):
        p = tmp_path / "decisions-2025-06-30.jsonl"
        p.write_text(
            json.dumps(_rec("2025-06-30T10:00:00+00:00"))
            + "\nnot json\n"
            + json.dumps(_rec("2025-06-30T11:00:00+00:00"))
            + "\n",
            encoding="utf-8",
        )
        assert len(search_logs(tmp_path)) == 2


# ── L: Malformed record skipped ─────────────────────────────────


class TestL_MalformedRecord:
    def test_missing_timestamp(self, tmp_path: Path):
        p = tmp_path / "decisions-2025-06-30.jsonl"
        good = _rec("2025-06-30T10:00:00+00:00")
        bad = {"selected_template": "x"}
        p.write_text(
            json.dumps(good) + "\n" + json.dumps(bad) + "\n", encoding="utf-8"
        )
        assert len(search_logs(tmp_path)) == 1

    def test_non_dict_skipped(self, tmp_path: Path):
        p = tmp_path / "decisions-2025-06-30.jsonl"
        p.write_text(
            json.dumps(_rec("2025-06-30T10:00:00+00:00"))
            + "\n"
            + json.dumps([1, 2, 3])
            + "\n",
            encoding="utf-8",
        )
        assert len(search_logs(tmp_path)) == 1


# ── M: Gzip read failure skipped ────────────────────────────────


class TestM_GzipFailure:
    def test_corrupt_gz_skipped(self, tmp_path: Path):
        (tmp_path / "decisions-2025-06-20.jsonl.gz").write_bytes(b"not gzip")
        _write(tmp_path, "2025-06-30", [_rec("2025-06-30T10:00:00+00:00")])
        assert len(search_logs(tmp_path)) == 1


# ── N: Newest-first ordering ────────────────────────────────────


class TestN_NewestFirst:
    def test_ordering(self, tmp_path: Path):
        _write(tmp_path, "2025-06-28", [_rec("2025-06-28T10:00:00+00:00")])
        _write(tmp_path, "2025-06-30", [_rec("2025-06-30T10:00:00+00:00")])
        _write(tmp_path, "2025-06-29", [_rec("2025-06-29T10:00:00+00:00")])
        results = search_logs(tmp_path)
        ts = [r["timestamp"] for r in results]
        assert ts == sorted(ts, reverse=True)


# ── O: Limit applied after filtering ────────────────────────────


class TestO_Limit:
    def test_limit_applied(self, tmp_path: Path):
        _write(
            tmp_path,
            "2025-06-30",
            [_rec(f"2025-06-30T{h:02d}:00:00+00:00") for h in range(10)],
        )
        results = search_logs(tmp_path, limit=3)
        assert len(results) == 3
        assert results[0]["timestamp"] > results[2]["timestamp"]

    def test_limit_larger_than_results(self, tmp_path: Path):
        _write(tmp_path, "2025-06-30", [_rec("2025-06-30T10:00:00+00:00")])
        results = search_logs(tmp_path, limit=100)
        assert len(results) == 1


# ── P: Zero-result human output ─────────────────────────────────


class TestP_ZeroHuman:
    def test_zero_human(self, tmp_path: Path):
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(app, ["logs", "search"])
        assert result.exit_code == 0
        assert "No matching records" in result.output


# ── Q: Zero-result JSON output ──────────────────────────────────


class TestQ_ZeroJson:
    def test_zero_json(self, tmp_path: Path):
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(app, ["logs", "search", "--json"])
        assert result.exit_code == 0
        assert json.loads(result.output) == []


# ── R: CLI --template ───────────────────────────────────────────


class TestR_CliTemplate:
    def test_template_filter(self, tmp_path: Path):
        _write(
            tmp_path,
            "2025-06-30",
            [
                _rec("2025-06-30T10:00:00+00:00", template="code-review"),
                _rec("2025-06-30T11:00:00+00:00", template="summarize"),
            ],
        )
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(
                app, ["logs", "search", "--template", "code-review", "--json"]
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["selected_template"] == "code-review"


# ── S: CLI --since ──────────────────────────────────────────────


class TestS_CliSince:
    def test_since_filter(self, tmp_path: Path):
        now = datetime.now(timezone.utc)
        recent = now - timedelta(hours=1)
        old = now - timedelta(days=30)
        _write(
            tmp_path,
            recent.strftime("%Y-%m-%d"),
            [_rec(recent.isoformat())],
        )
        _write(
            tmp_path,
            old.strftime("%Y-%m-%d"),
            [_rec(old.isoformat())],
        )
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(
                app, ["logs", "search", "--since", "7d", "--json"]
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1


# ── T: CLI --limit ──────────────────────────────────────────────


class TestT_CliLimit:
    def test_limit(self, tmp_path: Path):
        _write(
            tmp_path,
            "2025-06-30",
            [_rec(f"2025-06-30T{h:02d}:00:00+00:00") for h in range(10)],
        )
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(
                app, ["logs", "search", "--limit", "3", "--json"]
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 3


# ── U: CLI --json ───────────────────────────────────────────────


class TestU_CliJson:
    def test_json_output(self, tmp_path: Path):
        _write(tmp_path, "2025-06-30", [_rec("2025-06-30T10:00:00+00:00")])
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(app, ["logs", "search", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["timestamp"] == "2025-06-30T10:00:00+00:00"


# ── V: Invalid --since exits 1 ──────────────────────────────────


class TestV_InvalidSince:
    def test_bad_format(self, tmp_path: Path):
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(app, ["logs", "search", "--since", "abc"])
        assert result.exit_code == 1

    def test_natural_language_rejected(self, tmp_path: Path):
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(
                app, ["logs", "search", "--since", "1 hour ago"]
            )
        assert result.exit_code == 1


# ── W: Regression safety ────────────────────────────────────────


class TestW_Regression:
    def test_logs_callback(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path
        )
        result = runner.invoke(app, ["logs"])
        assert result.exit_code == 0

    def test_logs_json(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path
        )
        result = runner.invoke(app, ["logs", "--json"])
        assert result.exit_code == 0

    def test_prune(self, tmp_path: Path):
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(
                app, ["logs", "prune", "--before", "2025-01-01"]
            )
        assert result.exit_code == 0

    def test_rotate(self, tmp_path: Path):
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(app, ["logs", "rotate"])
        assert result.exit_code == 0

    def test_stats(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path
        )
        result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0
