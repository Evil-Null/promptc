"""Log rotation — gzip old decision logs, delete very old ones."""

from __future__ import annotations

import gzip
from dataclasses import dataclass
from datetime import date
from pathlib import Path

_PREFIX = "decisions-"
_JSONL = ".jsonl"
_GZ = ".jsonl.gz"

COMPRESS_AFTER_DAYS = 7
DELETE_AFTER_DAYS = 90


@dataclass(slots=True)
class RotationResult:
    """Summary of a rotation operation."""

    files_scanned: int = 0
    files_compressed: int = 0
    files_deleted: int = 0
    bytes_freed: int = 0
    skipped_files: int = 0
    dry_run: bool = False


def parse_rotatable_date(filename: str) -> tuple[date, bool] | None:
    """Extract date and compression state from a canonical log filename.

    Returns ``(date, is_compressed)`` or ``None`` for non-canonical names.
    """
    if not filename.startswith(_PREFIX):
        return None
    if filename.endswith(_GZ):
        stem = filename[len(_PREFIX) : -len(_GZ)]
        compressed = True
    elif filename.endswith(_JSONL):
        stem = filename[len(_PREFIX) : -len(_JSONL)]
        compressed = False
    else:
        return None
    try:
        return date.fromisoformat(stem), compressed
    except ValueError:
        return None


def rotate_logs(
    log_dir: Path,
    today: date,
    *,
    dry_run: bool = False,
) -> RotationResult:
    """Apply rotation policy to canonical decision logs.

    - Files younger than 7 days: untouched.
    - Files 7–89 days old: compress ``.jsonl`` to ``.jsonl.gz``.
    - Files 90+ days old: delete.
    """
    if not log_dir.is_dir():
        return RotationResult(dry_run=dry_run)

    canonical: list[tuple[date, Path, bool]] = []
    non_canonical = 0
    for p in log_dir.iterdir():
        if not p.is_file():
            continue
        parsed = parse_rotatable_date(p.name)
        if parsed is None:
            non_canonical += 1
            continue
        canonical.append((parsed[0], p, parsed[1]))

    result = RotationResult(
        files_scanned=len(canonical),
        skipped_files=non_canonical,
        dry_run=dry_run,
    )

    for file_date, path, is_gz in canonical:
        age = (today - file_date).days

        if age >= DELETE_AFTER_DAYS:
            _handle_delete(path, result, dry_run)
            continue

        if age >= COMPRESS_AFTER_DAYS and not is_gz:
            _handle_compress(path, result, dry_run)

    return result


def _handle_delete(path: Path, result: RotationResult, dry_run: bool) -> None:
    try:
        size = path.stat().st_size
    except OSError:
        result.skipped_files += 1
        return
    if dry_run:
        result.files_deleted += 1
        result.bytes_freed += size
        return
    try:
        path.unlink()
        result.files_deleted += 1
        result.bytes_freed += size
    except OSError:
        result.skipped_files += 1


def _handle_compress(path: Path, result: RotationResult, dry_run: bool) -> None:
    gz_path = path.parent / (path.name + ".gz")
    if gz_path.exists():
        return
    if dry_run:
        result.files_compressed += 1
        return
    try:
        raw = path.read_bytes()
        compressed = gzip.compress(raw)
        gz_path.write_bytes(compressed)
    except OSError:
        if gz_path.exists():
            try:
                gz_path.unlink()
            except OSError:
                pass
        result.skipped_files += 1
        return
    try:
        path.unlink()
    except OSError:
        pass
    result.files_compressed += 1
