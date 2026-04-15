"""Fire-and-forget JSONL decision log writer."""

from __future__ import annotations

import dataclasses
import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

_logger = logging.getLogger(__name__)

from interceptor.constants import LOG_DIR
from interceptor.observability.models import DecisionRecord


def get_log_dir(base: Path | None = None) -> Path:
    """Return (and create) the log directory."""
    d = base or LOG_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_daily_log_path(
    day: date | None = None, *, log_dir: Path | None = None
) -> Path:
    """Canonical JSONL path for *day* (defaults to today)."""
    return get_log_dir(log_dir) / f"decisions-{(day or datetime.now(timezone.utc).date()).isoformat()}.jsonl"


def log_decision(
    record: DecisionRecord, *, log_dir: Path | None = None
) -> None:
    """Append *record* as one JSON line.  Never raises."""
    try:
        d = get_log_dir(log_dir)
        day = record.timestamp[:10]
        path = d / f"decisions-{day}.jsonl"
        line = json.dumps(dataclasses.asdict(record), ensure_ascii=False)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        _logger.debug("decision log write failed", exc_info=True)


def read_daily_log(
    day: date | None = None, *, log_dir: Path | None = None
) -> list[dict]:
    """Read all records from the daily log.  Returns ``[]`` if missing."""
    d = log_dir or LOG_DIR
    path = d / f"decisions-{(day or datetime.now(timezone.utc).date()).isoformat()}.jsonl"
    if not path.exists():
        return []
    records: list[dict] = []
    try:
        raw_text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        _logger.debug("failed to read daily log %s", path, exc_info=True)
        return []
    for raw in raw_text.splitlines():
        raw = raw.strip()
        if raw:
            try:
                records.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
    return records
