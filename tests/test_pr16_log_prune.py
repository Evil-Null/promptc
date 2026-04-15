"""PR-16 tests — log retention and pruning."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from interceptor.cli import app
from interceptor.observability.log_prune import (
    PruneResult,
    enumerate_log_files,
    parse_log_date,
    prune_logs_before,
)

runner = CliRunner()

_CONTENT = '{"outcome":"success"}\n'


def _make_log(d: Path, name: str, content: str = _CONTENT) -> Path:
    p = d / name
    p.write_text(content, encoding="utf-8")
    return p


# ── A: Canonical filename parsing ────────────────────────────────────


class TestCanonicalFilenameParsing:
    def test_valid_date(self):
        assert parse_log_date("decisions-2025-01-15.jsonl") == date(2025, 1, 15)

    def test_leap_year(self):
        assert parse_log_date("decisions-2024-02-29.jsonl") == date(2024, 2, 29)

    def test_invalid_date_returns_none(self):
        assert parse_log_date("decisions-not-a-date.jsonl") is None


# ── B: Malformed filename ignored ────────────────────────────────────


class TestMalformedFilenameIgnored:
    def test_wrong_prefix(self):
        assert parse_log_date("logs-2025-01-15.jsonl") is None

    def test_wrong_suffix(self):
        assert parse_log_date("decisions-2025-01-15.json") is None

    def test_empty_string(self):
        assert parse_log_date("") is None

    def test_extra_segments_in_date(self):
        assert parse_log_date("decisions-2025-01-15-extra.jsonl") is None


# ── C: Sorted enumeration ────────────────────────────────────────────


class TestSortedEnumeration:
    def test_ascending_date_order(self, tmp_path: Path):
        _make_log(tmp_path, "decisions-2025-03-01.jsonl")
        _make_log(tmp_path, "decisions-2025-01-01.jsonl")
        _make_log(tmp_path, "decisions-2025-02-01.jsonl")
        entries = enumerate_log_files(tmp_path)
        dates = [d for d, _ in entries]
        assert dates == [date(2025, 1, 1), date(2025, 2, 1), date(2025, 3, 1)]

    def test_non_canonical_excluded(self, tmp_path: Path):
        _make_log(tmp_path, "decisions-2025-01-01.jsonl")
        _make_log(tmp_path, "random.txt")
        assert len(enumerate_log_files(tmp_path)) == 1

    def test_directories_excluded(self, tmp_path: Path):
        _make_log(tmp_path, "decisions-2025-01-01.jsonl")
        (tmp_path / "decisions-2025-02-01.jsonl").mkdir()
        assert len(enumerate_log_files(tmp_path)) == 1


# ── D: Prune older-than cutoff ───────────────────────────────────────


class TestPruneOlderThanCutoff:
    def test_deletes_older_files(self, tmp_path: Path):
        _make_log(tmp_path, "decisions-2025-01-01.jsonl")
        _make_log(tmp_path, "decisions-2025-01-02.jsonl")
        _make_log(tmp_path, "decisions-2025-01-03.jsonl")
        result = prune_logs_before(tmp_path, date(2025, 1, 3))
        assert result.files_deleted == 2
        assert not (tmp_path / "decisions-2025-01-01.jsonl").exists()
        assert not (tmp_path / "decisions-2025-01-02.jsonl").exists()
        assert (tmp_path / "decisions-2025-01-03.jsonl").exists()

    def test_empty_dir_zero_action(self, tmp_path: Path):
        result = prune_logs_before(tmp_path, date(2025, 1, 1))
        assert result.files_scanned == 0
        assert result.files_deleted == 0
        assert result.bytes_freed == 0

    def test_all_newer_none_deleted(self, tmp_path: Path):
        _make_log(tmp_path, "decisions-2025-06-01.jsonl")
        result = prune_logs_before(tmp_path, date(2025, 1, 1))
        assert result.files_deleted == 0
        assert (tmp_path / "decisions-2025-06-01.jsonl").exists()


# ── E: Cutoff date preserved ─────────────────────────────────────────


class TestCutoffDatePreserved:
    def test_exact_cutoff_not_deleted(self, tmp_path: Path):
        _make_log(tmp_path, "decisions-2025-01-15.jsonl")
        result = prune_logs_before(tmp_path, date(2025, 1, 15))
        assert result.files_deleted == 0
        assert (tmp_path / "decisions-2025-01-15.jsonl").exists()

    def test_day_before_cutoff_deleted(self, tmp_path: Path):
        _make_log(tmp_path, "decisions-2025-01-14.jsonl")
        _make_log(tmp_path, "decisions-2025-01-15.jsonl")
        result = prune_logs_before(tmp_path, date(2025, 1, 15))
        assert result.files_deleted == 1
        assert not (tmp_path / "decisions-2025-01-14.jsonl").exists()
        assert (tmp_path / "decisions-2025-01-15.jsonl").exists()


# ── F: Unrelated files preserved ─────────────────────────────────────


class TestUnrelatedFilesPreserved:
    def test_non_log_files_untouched(self, tmp_path: Path):
        _make_log(tmp_path, "decisions-2025-01-01.jsonl")
        _make_log(tmp_path, "notes.txt", "keep me")
        _make_log(tmp_path, "config.toml", "[settings]")
        result = prune_logs_before(tmp_path, date(2025, 6, 1))
        assert result.files_deleted == 1
        assert (tmp_path / "notes.txt").exists()
        assert (tmp_path / "config.toml").exists()

    def test_skipped_counts_non_canonical(self, tmp_path: Path):
        _make_log(tmp_path, "decisions-2025-01-01.jsonl")
        _make_log(tmp_path, "notes.txt")
        _make_log(tmp_path, "readme.md")
        result = prune_logs_before(tmp_path, date(2025, 6, 1))
        assert result.skipped_files == 2


# ── G: Dry-run deletes nothing ───────────────────────────────────────


class TestDryRunDeletesNothing:
    def test_files_remain_on_disk(self, tmp_path: Path):
        _make_log(tmp_path, "decisions-2025-01-01.jsonl")
        _make_log(tmp_path, "decisions-2025-01-02.jsonl")
        result = prune_logs_before(tmp_path, date(2025, 6, 1), dry_run=True)
        assert result.files_deleted == 2
        assert result.dry_run is True
        assert (tmp_path / "decisions-2025-01-01.jsonl").exists()
        assert (tmp_path / "decisions-2025-01-02.jsonl").exists()

    def test_bytes_freed_reported(self, tmp_path: Path):
        _make_log(tmp_path, "decisions-2025-01-01.jsonl", "x" * 100)
        result = prune_logs_before(tmp_path, date(2025, 6, 1), dry_run=True)
        assert result.bytes_freed == 100
        assert (tmp_path / "decisions-2025-01-01.jsonl").exists()


# ── H: Missing log dir -> zero-action result ─────────────────────────


class TestMissingLogDir:
    def test_nonexistent_dir(self, tmp_path: Path):
        missing = tmp_path / "no-such-dir"
        result = prune_logs_before(missing, date(2025, 1, 1))
        assert result.files_scanned == 0
        assert result.files_deleted == 0
        assert result.bytes_freed == 0

    def test_enumerate_nonexistent(self, tmp_path: Path):
        missing = tmp_path / "no-such-dir"
        assert enumerate_log_files(missing) == []


# ── I: Bytes freed computed correctly ─────────────────────────────────


class TestBytesFreedComputed:
    def test_single_file_bytes(self, tmp_path: Path):
        content = '{"ok":true}\n' * 10
        _make_log(tmp_path, "decisions-2025-01-01.jsonl", content)
        result = prune_logs_before(tmp_path, date(2025, 6, 1))
        assert result.bytes_freed == len(content.encode("utf-8"))

    def test_multiple_files_sum(self, tmp_path: Path):
        c1 = "a" * 50
        c2 = "b" * 75
        _make_log(tmp_path, "decisions-2025-01-01.jsonl", c1)
        _make_log(tmp_path, "decisions-2025-01-02.jsonl", c2)
        result = prune_logs_before(tmp_path, date(2025, 6, 1))
        assert result.bytes_freed == 125

    def test_preserved_files_not_counted(self, tmp_path: Path):
        _make_log(tmp_path, "decisions-2025-01-01.jsonl", "a" * 50)
        _make_log(tmp_path, "decisions-2025-06-01.jsonl", "b" * 200)
        result = prune_logs_before(tmp_path, date(2025, 3, 1))
        assert result.bytes_freed == 50


# ── J: CLI human output ──────────────────────────────────────────────


class TestCliHumanOutput:
    def test_basic_prune(self, tmp_path: Path):
        _make_log(tmp_path, "decisions-2025-01-01.jsonl")
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(app, ["logs", "prune", "--before", "2025-06-01"])
        assert result.exit_code == 0
        assert "Deleted" in result.output
        assert "1" in result.output

    def test_no_files_to_prune(self, tmp_path: Path):
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(app, ["logs", "prune", "--before", "2025-01-01"])
        assert result.exit_code == 0
        assert "0" in result.output

    def test_dry_run_label(self, tmp_path: Path):
        _make_log(tmp_path, "decisions-2025-01-01.jsonl")
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(
                app, ["logs", "prune", "--before", "2025-06-01", "--dry-run"]
            )
        assert result.exit_code == 0
        assert "dry run" in result.output.lower()


# ── K: CLI invalid date ──────────────────────────────────────────────


class TestCliInvalidDate:
    def test_bad_format_exit_1(self):
        result = runner.invoke(app, ["logs", "prune", "--before", "not-a-date"])
        assert result.exit_code == 1
        assert "Invalid date" in result.output

    def test_month_out_of_range_exit_1(self):
        result = runner.invoke(app, ["logs", "prune", "--before", "2025-13-01"])
        assert result.exit_code == 1


# ── L: CLI dry-run ───────────────────────────────────────────────────


class TestCliDryRun:
    def test_files_not_deleted(self, tmp_path: Path):
        _make_log(tmp_path, "decisions-2025-01-01.jsonl")
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(
                app, ["logs", "prune", "--before", "2025-06-01", "--dry-run"]
            )
        assert result.exit_code == 0
        assert (tmp_path / "decisions-2025-01-01.jsonl").exists()

    def test_count_shown(self, tmp_path: Path):
        _make_log(tmp_path, "decisions-2025-01-01.jsonl")
        _make_log(tmp_path, "decisions-2025-01-02.jsonl")
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(
                app, ["logs", "prune", "--before", "2025-06-01", "--dry-run"]
            )
        assert "2" in result.output


# ── M: CLI JSON output ───────────────────────────────────────────────


class TestCliJsonOutput:
    def test_valid_json(self, tmp_path: Path):
        _make_log(tmp_path, "decisions-2025-01-01.jsonl")
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(
                app, ["logs", "prune", "--before", "2025-06-01", "--json"]
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["files_deleted"] == 1
        assert data["dry_run"] is False

    def test_dry_run_json(self, tmp_path: Path):
        _make_log(tmp_path, "decisions-2025-01-01.jsonl")
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(
                app,
                ["logs", "prune", "--before", "2025-06-01", "--dry-run", "--json"],
            )
        data = json.loads(result.output)
        assert data["files_deleted"] == 1
        assert data["dry_run"] is True

    def test_json_has_all_fields(self, tmp_path: Path):
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(
                app, ["logs", "prune", "--before", "2025-01-01", "--json"]
            )
        data = json.loads(result.output)
        for key in (
            "files_scanned",
            "files_deleted",
            "bytes_freed",
            "skipped_files",
            "dry_run",
        ):
            assert key in data


# ── N: Partial deletion failure ──────────────────────────────────────


class TestPartialDeletionFailure:
    def test_unlink_oserror_skipped(self, tmp_path: Path):
        _make_log(tmp_path, "decisions-2025-01-01.jsonl")
        _make_log(tmp_path, "decisions-2025-01-02.jsonl")
        original_unlink = Path.unlink

        def _flaky_unlink(self_path, *args, **kwargs):
            if "01-01" in self_path.name:
                raise OSError("permission denied")
            return original_unlink(self_path, *args, **kwargs)

        with patch.object(Path, "unlink", _flaky_unlink):
            result = prune_logs_before(tmp_path, date(2025, 6, 1))
        assert result.files_deleted == 1
        assert result.skipped_files >= 1
        assert (tmp_path / "decisions-2025-01-01.jsonl").exists()
        assert not (tmp_path / "decisions-2025-01-02.jsonl").exists()

    def test_stat_oserror_skipped(self, tmp_path: Path):
        p = _make_log(tmp_path, "decisions-2025-01-01.jsonl")
        from interceptor.observability.log_prune import enumerate_log_files as _enum

        def _enum_then_remove(log_dir):
            entries = _enum(log_dir)
            p.unlink()
            return entries

        with patch(
            "interceptor.observability.log_prune.enumerate_log_files",
            _enum_then_remove,
        ):
            result = prune_logs_before(tmp_path, date(2025, 6, 1))
        assert result.files_deleted == 0
        assert result.skipped_files >= 1


# ── O: Regression safety ─────────────────────────────────────────────


class TestRegressionSafety:
    def test_logs_command_still_works(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path
        )
        result = runner.invoke(app, ["logs"])
        assert result.exit_code == 0

    def test_logs_json_still_works(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path
        )
        result = runner.invoke(app, ["logs", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "total" in data

    def test_stats_command_still_works(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path
        )
        result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0

    def test_read_daily_log_unmodified(self, tmp_path: Path):
        from interceptor.observability.decision_log import read_daily_log

        assert read_daily_log(log_dir=tmp_path) == []

    def test_aggregate_unmodified(self):
        from interceptor.observability.metrics import aggregate

        snap = aggregate([])
        assert snap.total_decisions == 0
