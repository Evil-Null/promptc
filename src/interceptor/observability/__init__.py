"""Observability — decision logging, derived metrics, and log lifecycle."""

from interceptor.observability.decision_log import (
    get_daily_log_path,
    get_log_dir,
    log_decision,
    read_daily_log,
)
from interceptor.observability.log_prune import (
    PruneResult,
    enumerate_log_files,
    parse_log_date,
    prune_logs_before,
)
from interceptor.observability.log_rotate import (
    RotationResult,
    parse_rotatable_date,
    rotate_logs,
)
from interceptor.observability.log_search import parse_since, search_logs
from interceptor.observability.metrics import StatsSnapshot, TemplateUsage, aggregate
from interceptor.observability.models import DecisionRecord

__all__ = [
    "DecisionRecord",
    "PruneResult",
    "RotationResult",
    "StatsSnapshot",
    "TemplateUsage",
    "aggregate",
    "enumerate_log_files",
    "get_daily_log_path",
    "get_log_dir",
    "log_decision",
    "parse_log_date",
    "parse_rotatable_date",
    "parse_since",
    "prune_logs_before",
    "read_daily_log",
    "rotate_logs",
    "search_logs",
]
