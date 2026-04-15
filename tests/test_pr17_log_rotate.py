"""PR-17 tests — log rotation."""

from __future__ import annotations

import gzip
import json
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from interceptor.cli import app
from interceptor.observability.log_rotate import (
    RotationResult,
    parse_rotatable_date,
    rotate_logs,
)

runner = CliRunner()

_CONTENT = '{"outcome":"success"}\n'
_TODAY = date(2025, 7, 1)


def _make_log(d: Path, name: str, content: str = _CONTENT) -> Path:
    p = d / name
    p.write_text(content, encoding="utf-8")
    return p


def _make_gz(d: Path, name: str, content: str = _CONTENT) -> Path:
    p = d / name
    p.write_bytes(gzip.compress(content.encode("utf-8")))
    return p


def _days_ago(n: int) -> str:
    """Filename-safe ISO date string *n* days before today."""
    return (date.today() - timedelta(days=n)).isoformat()


# ── A: Parse canonical .jsonl filename ───────────────────────────


class TestParseJsonl:
    def test_valid_date(self):
        assert parse_rotatable_date("decisions-2025-01-15.jsonl") == (
            date(2025, 1, 15),
            False,
        )

    def test_leap_year(self):
        assert parse_rotatable_date("decisions-2024-02-29.jsonl") == (
            date(2024, 2, 29),
            False,
        )


# ── B: Parse canonical .jsonl.gz filename ────────────────────────


class TestParseGz:
    def test_valid_gz(self):
        assert parse_rotatable_date("decisions-2025-01-15.jsonl.gz") == (
            date(2025, 1, 15),
            True,
        )

    def test_leap_year_gz(self):
        assert parse_rotatable_date("decisions-2024-02-29.jsonl.gz") == (
            date(2024, 2, 29),
            True,
        )


# ── C: Malformed filename ignored ───────────────────────────────


class TestMalformedIgnored:
    def test_wrong_prefix(self):
        assert parse_rotatable_date("logs-2025-01-15.jsonl") is None

    def test_wrong_suffix(self):
        assert parse_rotatable_date("decisions-2025-01-15.json") is None

    def test_empty(self):
        assert parse_rotatable_date("") is None

    def test_extra_segments(self):
        assert parse_rotatable_date("decisions-2025-01-15-extra.jsonl") is None

    def test_invalid_date_gz(self):
        assert parse_rotatable_date("decisions-bad.jsonl.gz") is None


# ── D: Younger-than-7d unchanged ────────────────────────────────


class TestYoungerUnchanged:
    def test_six_days_old(self, tmp_path: Path):
        _make_log(tmp_path, "decisions-2025-06-25.jsonl")  # 6 days
        result = rotate_logs(tmp_path, _TODAY)
        assert result.files_compressed == 0
        assert result.files_deleted == 0
        assert (tmp_path / "decisions-2025-06-25.jsonl").exists()

    def test_today_untouched(self, tmp_path: Path):
        _make_log(tmp_path, "decisions-2025-07-01.jsonl")  # 0 days
        result = rotate_logs(tmp_path, _TODAY)
        assert result.files_compressed == 0
        assert result.files_deleted == 0


# ── E: Exactly-7d .jsonl compresses ─────────────────────────────


class TestExact7dCompresses:
    def test_exactly_7_days(self, tmp_path: Path):
        _make_log(tmp_path, "decisions-2025-06-24.jsonl")  # 7 days
        result = rotate_logs(tmp_path, _TODAY)
        assert result.files_compressed == 1
        assert not (tmp_path / "decisions-2025-06-24.jsonl").exists()
        assert (tmp_path / "decisions-2025-06-24.jsonl.gz").exists()


# ── F: 7-89d .jsonl compresses ──────────────────────────────────


class TestMidRangeCompresses:
    def test_30_days_old(self, tmp_path: Path):
        _make_log(tmp_path, "decisions-2025-06-01.jsonl")  # 30 days
        result = rotate_logs(tmp_path, _TODAY)
        assert result.files_compressed == 1
        assert (tmp_path / "decisions-2025-06-01.jsonl.gz").exists()

    def test_89_days_old(self, tmp_path: Path):
        _make_log(tmp_path, "decisions-2025-04-03.jsonl")  # 89 days
        result = rotate_logs(tmp_path, _TODAY)
        assert result.files_compressed == 1
        assert not (tmp_path / "decisions-2025-04-03.jsonl").exists()


# ── G: Already .gz in 7-89d unchanged ───────────────────────────


class TestAlreadyGzUnchanged:
    def test_gz_in_range(self, tmp_path: Path):
        _make_gz(tmp_path, "decisions-2025-06-01.jsonl.gz")  # 30 days, already gz
        result = rotate_logs(tmp_path, _TODAY)
        assert result.files_compressed == 0
        assert result.files_deleted == 0
        assert (tmp_path / "decisions-2025-06-01.jsonl.gz").exists()


# ── H: Exactly-90d deleted ──────────────────────────────────────


class TestExact90dDeleted:
    def test_jsonl(self, tmp_path: Path):
        _make_log(tmp_path, "decisions-2025-04-02.jsonl")  # 90 days
        result = rotate_logs(tmp_path, _TODAY)
        assert result.files_deleted == 1
        assert not (tmp_path / "decisions-2025-04-02.jsonl").exists()

    def test_gz(self, tmp_path: Path):
        _make_gz(tmp_path, "decisions-2025-04-02.jsonl.gz")  # 90 days
        result = rotate_logs(tmp_path, _TODAY)
        assert result.files_deleted == 1
        assert not (tmp_path / "decisions-2025-04-02.jsonl.gz").exists()


# ── I: >90d .jsonl deleted ──────────────────────────────────────


class TestOldJsonlDeleted:
    def test_180_days(self, tmp_path: Path):
        _make_log(tmp_path, "decisions-2025-01-02.jsonl")  # 180 days
        result = rotate_logs(tmp_path, _TODAY)
        assert result.files_deleted == 1
        assert result.bytes_freed > 0


# ── J: >90d .jsonl.gz deleted ───────────────────────────────────


class TestOldGzDeleted:
    def test_180_days_gz(self, tmp_path: Path):
        _make_gz(tmp_path, "decisions-2025-01-02.jsonl.gz")  # 180 days
        result = rotate_logs(tmp_path, _TODAY)
        assert result.files_deleted == 1
        assert not (tmp_path / "decisions-2025-01-02.jsonl.gz").exists()


# ── K: Delete wins over compress ────────────────────────────────


class TestDeleteWinsOverCompress:
    def test_at_90d_boundary(self, tmp_path: Path):
        _make_log(tmp_path, "decisions-2025-04-02.jsonl")  # 90 days
        result = rotate_logs(tmp_path, _TODAY)
        assert result.files_deleted == 1
        assert result.files_compressed == 0
        assert not (tmp_path / "decisions-2025-04-02.jsonl").exists()
        assert not (tmp_path / "decisions-2025-04-02.jsonl.gz").exists()


# ── L: Dry-run compresses nothing ───────────────────────────────


class TestDryRunNoCompress:
    def test_files_remain(self, tmp_path: Path):
        _make_log(tmp_path, "decisions-2025-06-01.jsonl")  # 30 days
        result = rotate_logs(tmp_path, _TODAY, dry_run=True)
        assert result.files_compressed == 1
        assert result.dry_run is True
        assert (tmp_path / "decisions-2025-06-01.jsonl").exists()
        assert not (tmp_path / "decisions-2025-06-01.jsonl.gz").exists()


# ── M: Dry-run deletes nothing ──────────────────────────────────


class TestDryRunNoDelete:
    def test_files_remain(self, tmp_path: Path):
        _make_log(tmp_path, "decisions-2025-01-01.jsonl")  # 181 days
        result = rotate_logs(tmp_path, _TODAY, dry_run=True)
        assert result.files_deleted == 1
        assert result.bytes_freed > 0
        assert result.dry_run is True
        assert (tmp_path / "decisions-2025-01-01.jsonl").exists()


# ── N: Missing dir -> zero-action ───────────────────────────────


class TestMissingDir:
    def test_nonexistent(self, tmp_path: Path):
        result = rotate_logs(tmp_path / "nope", _TODAY)
        assert result.files_scanned == 0
        assert result.files_compressed == 0
        assert result.files_deleted == 0


# ── O: Unrelated files preserved ────────────────────────────────


class TestUnrelatedPreserved:
    def test_non_log_untouched(self, tmp_path: Path):
        _make_log(tmp_path, "decisions-2025-01-01.jsonl")
        _make_log(tmp_path, "notes.txt", "keep me")
        _make_log(tmp_path, "random.jsonl.gz", "random")
        result = rotate_logs(tmp_path, _TODAY)
        assert (tmp_path / "notes.txt").exists()
        assert (tmp_path / "random.jsonl.gz").exists()
        assert result.skipped_files == 2

    def test_directory_ignored(self, tmp_path: Path):
        (tmp_path / "decisions-2025-01-01.jsonl").mkdir()
        result = rotate_logs(tmp_path, _TODAY)
        assert result.files_scanned == 0


# ── P: Compression preserves content ────────────────────────────


class TestCompressionContent:
    def test_roundtrip(self, tmp_path: Path):
        content = '{"outcome":"success","template":"qa"}\n' * 100
        _make_log(tmp_path, "decisions-2025-06-01.jsonl", content)
        rotate_logs(tmp_path, _TODAY)
        gz_path = tmp_path / "decisions-2025-06-01.jsonl.gz"
        assert gz_path.exists()
        restored = gzip.decompress(gz_path.read_bytes()).decode("utf-8")
        assert restored == content


# ── Q: Existing .gz not overwritten ─────────────────────────────


class TestExistingGzSafe:
    def test_no_overwrite(self, tmp_path: Path):
        original_gz = b"original compressed data"
        (tmp_path / "decisions-2025-06-01.jsonl.gz").write_bytes(original_gz)
        _make_log(tmp_path, "decisions-2025-06-01.jsonl")
        result = rotate_logs(tmp_path, _TODAY)
        assert (tmp_path / "decisions-2025-06-01.jsonl").exists()
        assert (tmp_path / "decisions-2025-06-01.jsonl.gz").read_bytes() == original_gz
        assert result.files_compressed == 0


# ── R: Compression failure preserves original ────────────────────


class TestCompressionFailure:
    def test_read_failure(self, tmp_path: Path):
        _make_log(tmp_path, "decisions-2025-06-01.jsonl")
        original_read = Path.read_bytes

        def _fail_read(self_path, *a, **kw):
            if "06-01" in self_path.name and self_path.suffix == ".jsonl":
                raise OSError("permission denied")
            return original_read(self_path, *a, **kw)

        with patch.object(Path, "read_bytes", _fail_read):
            result = rotate_logs(tmp_path, _TODAY)
        assert result.files_compressed == 0
        assert result.skipped_files >= 1
        assert (tmp_path / "decisions-2025-06-01.jsonl").exists()
        assert not (tmp_path / "decisions-2025-06-01.jsonl.gz").exists()


# ── S: Delete failure increments skipped ─────────────────────────


class TestDeleteFailure:
    def test_unlink_failure(self, tmp_path: Path):
        _make_log(tmp_path, "decisions-2025-01-01.jsonl")  # 181 days
        original_unlink = Path.unlink

        def _fail_unlink(self_path, *a, **kw):
            if "01-01" in self_path.name and self_path.name.endswith(".jsonl"):
                raise OSError("permission denied")
            return original_unlink(self_path, *a, **kw)

        with patch.object(Path, "unlink", _fail_unlink):
            result = rotate_logs(tmp_path, _TODAY)
        assert result.files_deleted == 0
        assert result.skipped_files >= 1
        assert (tmp_path / "decisions-2025-01-01.jsonl").exists()


# ── T: Idempotence ──────────────────────────────────────────────


class TestIdempotence:
    def test_double_run(self, tmp_path: Path):
        _make_log(tmp_path, "decisions-2025-06-01.jsonl")  # 30d → compress
        _make_log(tmp_path, "decisions-2025-01-01.jsonl")  # 181d → delete
        _make_log(tmp_path, "decisions-2025-06-30.jsonl")  # 1d → keep

        r1 = rotate_logs(tmp_path, _TODAY)
        assert r1.files_compressed == 1
        assert r1.files_deleted == 1

        r2 = rotate_logs(tmp_path, _TODAY)
        assert r2.files_compressed == 0
        assert r2.files_deleted == 0

        assert (tmp_path / "decisions-2025-06-01.jsonl.gz").exists()
        assert (tmp_path / "decisions-2025-06-30.jsonl").exists()
        assert not (tmp_path / "decisions-2025-01-01.jsonl").exists()

    def test_triple_run(self, tmp_path: Path):
        _make_log(tmp_path, "decisions-2025-05-01.jsonl")  # 61d → compress
        rotate_logs(tmp_path, _TODAY)
        rotate_logs(tmp_path, _TODAY)
        r3 = rotate_logs(tmp_path, _TODAY)
        assert r3.files_compressed == 0
        assert r3.files_deleted == 0
        assert (tmp_path / "decisions-2025-05-01.jsonl.gz").exists()


# ── U: CLI human output ─────────────────────────────────────────


class TestCliHuman:
    def test_delete_shown(self, tmp_path: Path):
        _make_log(tmp_path, f"decisions-{_days_ago(100)}.jsonl")
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(app, ["logs", "rotate"])
        assert result.exit_code == 0
        assert "Deleted" in result.output

    def test_empty_dir(self, tmp_path: Path):
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(app, ["logs", "rotate"])
        assert result.exit_code == 0
        assert "0" in result.output

    def test_compress_shown(self, tmp_path: Path):
        _make_log(tmp_path, f"decisions-{_days_ago(30)}.jsonl")
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(app, ["logs", "rotate"])
        assert result.exit_code == 0
        assert "Compressed" in result.output


# ── V: CLI dry-run output ───────────────────────────────────────


class TestCliDryRun:
    def test_label_and_preserved(self, tmp_path: Path):
        name = f"decisions-{_days_ago(100)}.jsonl"
        _make_log(tmp_path, name)
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(app, ["logs", "rotate", "--dry-run"])
        assert result.exit_code == 0
        assert "dry run" in result.output.lower()
        assert (tmp_path / name).exists()


# ── W: CLI JSON output ──────────────────────────────────────────


class TestCliJson:
    def test_valid_json(self, tmp_path: Path):
        _make_log(tmp_path, f"decisions-{_days_ago(100)}.jsonl")
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(app, ["logs", "rotate", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["files_deleted"] >= 1

    def test_all_fields(self, tmp_path: Path):
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(app, ["logs", "rotate", "--json"])
        data = json.loads(result.output)
        for key in (
            "files_scanned",
            "files_compressed",
            "files_deleted",
            "bytes_freed",
            "skipped_files",
            "dry_run",
        ):
            assert key in data


# ── X: Regression safety ────────────────────────────────────────


class TestRegressionSafety:
    def test_logs_command(self, tmp_path: Path, monkeypatch):
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
        data = json.loads(result.output)
        assert "total" in data

    def test_prune_works(self, tmp_path: Path):
        with patch("interceptor.constants.LOG_DIR", tmp_path):
            result = runner.invoke(app, ["logs", "prune", "--before", "2025-01-01"])
        assert result.exit_code == 0

    def test_stats_works(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path
        )
        result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0

    def test_aggregate_unmodified(self):
        from interceptor.observability.metrics import aggregate

        snap = aggregate([])
        assert snap.total_decisions == 0
