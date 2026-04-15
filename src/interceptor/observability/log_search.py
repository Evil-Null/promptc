"""Search across canonical decision log files."""

from __future__ import annotations

import gzip
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

_PREFIX = "decisions-"
_JSONL = ".jsonl"
_GZ = ".jsonl.gz"
_SINCE_RE = re.compile(r"^(\d+)([mhd])$")


def parse_since(text: str) -> timedelta | None:
    """Parse ``30m``, ``1h``, or ``7d`` into a timedelta."""
    m = _SINCE_RE.match(text.strip())
    if m is None:
        return None
    value, unit = int(m.group(1)), m.group(2)
    if unit == "m":
        return timedelta(minutes=value)
    if unit == "h":
        return timedelta(hours=value)
    return timedelta(days=value)


def _is_canonical(filename: str) -> tuple[bool, bool]:
    """Return ``(is_canonical, is_gz)``."""
    if not filename.startswith(_PREFIX):
        return False, False
    if filename.endswith(_GZ):
        stem = filename[len(_PREFIX) : -len(_GZ)]
        is_gz = True
    elif filename.endswith(_JSONL):
        stem = filename[len(_PREFIX) : -len(_JSONL)]
        is_gz = False
    else:
        return False, False
    try:
        date.fromisoformat(stem)
    except ValueError:
        return False, False
    return True, is_gz


def _read_lines(path: Path, is_gz: bool) -> list[str]:
    """Read JSONL lines from a plain or gzipped file."""
    if is_gz:
        raw = gzip.decompress(path.read_bytes()).decode("utf-8")
    else:
        raw = path.read_text(encoding="utf-8")
    return [ln for ln in raw.splitlines() if ln.strip()]


def search_logs(
    log_dir: Path,
    *,
    template: str | None = None,
    since: timedelta | None = None,
    now: datetime | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Search decision log records across canonical files.

    Returns matching records newest-first.  Malformed lines and
    unreadable files are silently skipped.
    """
    if not log_dir.is_dir():
        return []

    now_dt = now or datetime.now(timezone.utc)
    cutoff = (now_dt - since) if since is not None else None

    records: list[tuple[str, dict]] = []

    for p in log_dir.iterdir():
        if not p.is_file():
            continue
        canonical, is_gz = _is_canonical(p.name)
        if not canonical:
            continue

        try:
            lines = _read_lines(p, is_gz)
        except (OSError, gzip.BadGzipFile, UnicodeDecodeError):
            continue

        for line in lines:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict):
                continue

            ts_str = rec.get("timestamp")
            if not isinstance(ts_str, str) or not ts_str:
                continue

            if template is not None and rec.get("selected_template") != template:
                continue

            if cutoff is not None:
                try:
                    ts_dt = datetime.fromisoformat(ts_str)
                    if ts_dt.tzinfo is None:
                        ts_dt = ts_dt.replace(tzinfo=timezone.utc)
                    if ts_dt < cutoff:
                        continue
                except ValueError:
                    continue

            records.append((ts_str, rec))

    records.sort(key=lambda x: x[0], reverse=True)
    result = [r[1] for r in records]
    if limit is not None:
        result = result[:limit]
    return result
