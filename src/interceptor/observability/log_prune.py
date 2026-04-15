"""Log file enumeration and safe pruning."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

_PREFIX = "decisions-"
_SUFFIX = ".jsonl"


@dataclass(slots=True)
class PruneResult:
    """Summary of a prune operation."""

    files_scanned: int = 0
    files_deleted: int = 0
    bytes_freed: int = 0
    skipped_files: int = 0
    dry_run: bool = False


def parse_log_date(filename: str) -> date | None:
    """Extract the date from a canonical decision-log filename."""
    if not filename.startswith(_PREFIX) or not filename.endswith(_SUFFIX):
        return None
    stem = filename[len(_PREFIX) : -len(_SUFFIX)]
    try:
        return date.fromisoformat(stem)
    except ValueError:
        return None


def enumerate_log_files(log_dir: Path) -> list[tuple[date, Path]]:
    """List canonical decision log files sorted by date ascending."""
    if not log_dir.is_dir():
        return []
    results: list[tuple[date, Path]] = []
    for p in log_dir.iterdir():
        if not p.is_file():
            continue
        d = parse_log_date(p.name)
        if d is not None:
            results.append((d, p))
    results.sort(key=lambda x: x[0])
    return results


def prune_logs_before(
    log_dir: Path, before: date, *, dry_run: bool = False
) -> PruneResult:
    """Delete canonical decision logs strictly older than *before*.

    Non-canonical files are never touched.  The cutoff date itself is preserved.
    """
    entries = enumerate_log_files(log_dir)
    non_canonical = sum(
        1
        for p in (log_dir.iterdir() if log_dir.is_dir() else [])
        if p.is_file() and parse_log_date(p.name) is None
    )
    result = PruneResult(
        files_scanned=len(entries),
        skipped_files=non_canonical,
        dry_run=dry_run,
    )
    for d, p in entries:
        if d >= before:
            continue
        try:
            size = p.stat().st_size
        except OSError:
            result.skipped_files += 1
            continue
        if dry_run:
            result.files_deleted += 1
            result.bytes_freed += size
        else:
            try:
                p.unlink()
                result.files_deleted += 1
                result.bytes_freed += size
            except OSError:
                result.skipped_files += 1
    return result
