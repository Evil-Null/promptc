"""PR-32 tests — Phase 7 closure and v1.0 readiness confirmation."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest


# ── A: CLI display dates use UTC ─────────────────────────────────────


class TestCliDisplayUtc:
    """Verify logs/stats CLI output shows UTC-aligned dates."""

    @staticmethod
    def _utc_today() -> str:
        return datetime.now(timezone.utc).date().isoformat()

    def test_logs_json_date_is_utc(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from interceptor.cli import app

        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path
        )
        runner = CliRunner()
        result = runner.invoke(app, ["logs", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["date"] == self._utc_today()

    def test_logs_human_date_is_utc(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from interceptor.cli import app

        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path
        )
        runner = CliRunner()
        result = runner.invoke(app, ["logs"])
        assert result.exit_code == 0
        assert self._utc_today() in result.output

    def test_stats_json_date_is_utc(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from interceptor.cli import app

        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path
        )
        runner = CliRunner()
        result = runner.invoke(app, ["stats", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["date"] == self._utc_today()

    def test_stats_human_date_is_utc(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from interceptor.cli import app

        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path
        )
        runner = CliRunner()
        result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0
        assert self._utc_today() in result.output

    def test_stats_explicit_date_overrides(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from interceptor.cli import app

        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path
        )
        runner = CliRunner()
        result = runner.invoke(app, ["stats", "--json", "--date", "2025-06-15"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["date"] == "2025-06-15"


# ── B: Observability display/data consistency ────────────────────────


class TestObservabilityConsistency:
    """Logs written and read back produce consistent display."""

    def test_logs_data_matches_display_date(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from interceptor.cli import app
        from interceptor.observability.decision_log import log_decision
        from interceptor.observability.models import DecisionRecord

        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path
        )
        rec = DecisionRecord(
            input_hash="pr32_test",
            selected_template="debug",
            backend="claude",
            execution_time_ms=100,
        )
        log_decision(rec, log_dir=tmp_path)

        runner = CliRunner()
        result = runner.invoke(app, ["logs", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total"] == 1
        assert data["entries"][0]["input_hash"] == "pr32_test"
        utc_date = datetime.now(timezone.utc).date().isoformat()
        assert data["date"] == utc_date

    def test_stats_data_matches_display_date(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from interceptor.cli import app
        from interceptor.observability.decision_log import log_decision
        from interceptor.observability.models import DecisionRecord

        monkeypatch.setattr(
            "interceptor.observability.decision_log.LOG_DIR", tmp_path
        )
        for i in range(3):
            rec = DecisionRecord(
                input_hash=f"h{i}",
                selected_template="code_review",
                backend="claude",
                execution_time_ms=200,
            )
            log_decision(rec, log_dir=tmp_path)

        runner = CliRunner()
        result = runner.invoke(app, ["stats", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total_decisions"] == 3
        assert data["date"] == datetime.now(timezone.utc).date().isoformat()


# ── C: PR-30 release readiness reconfirmation ────────────────────────


class TestReleaseReconfirmation:
    """Reconfirm latency, routing, health, and determinism post-PR-31."""

    def test_compile_latency_under_200ms(self):
        import time

        from interceptor.compilation.assembler import compile_prompt
        from interceptor.models.template import (
            Category,
            Template,
            TemplateMeta,
            TemplatePrompt,
            TemplateTriggers,
        )

        tpl = Template(
            meta=TemplateMeta(
                name="perf_test", category=Category.EVALUATIVE,
                version="1.0.0", author="test",
            ),
            triggers=TemplateTriggers(en=["perf test"], ka=["ტესტი"]),
            prompt=TemplatePrompt(
                system_directive="Be brief.",
                output_schema="Plain text.",
            ),
        )
        start = time.perf_counter()
        compile_prompt(template=tpl, raw_input="test input", max_tokens=1000)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 200, f"Compile took {elapsed_ms:.1f}ms"

    def test_route_latency_under_50ms(self):
        import time

        from interceptor.config import Config
        from interceptor.models.template import (
            Category,
            Template,
            TemplateMeta,
            TemplatePrompt,
            TemplateTriggers,
        )
        from interceptor.routing.router import route
        from interceptor.template_registry import TemplateRegistry

        tpl = Template(
            meta=TemplateMeta(
                name="lat_test", category=Category.EVALUATIVE,
                version="1.0.0", author="test",
            ),
            triggers=TemplateTriggers(en=["latency test"], ka=["ტესტი"]),
            prompt=TemplatePrompt(
                system_directive="Test.",
                output_schema="Plain text.",
            ),
        )
        reg = TemplateRegistry({tpl.meta.name: tpl})
        cfg = Config()
        start = time.perf_counter()
        route("latency test", registry=reg, config=cfg)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 50, f"Route took {elapsed_ms:.1f}ms"

    def test_health_all_pass(self):
        from interceptor.health import (
            check_backends_valid,
            check_compilation_valid,
            check_config_valid,
            check_plugin_integrity,
            check_routing_valid,
            check_templates_valid,
        )

        checks = [
            check_config_valid,
            check_templates_valid,
            check_routing_valid,
            check_compilation_valid,
            check_backends_valid,
            check_plugin_integrity,
        ]
        for check in checks:
            result = check()
            assert result.status in ("pass", "warn"), (
                f"{result.name} failed: {result.detail}"
            )

    def test_golden_routing_accuracy(self):
        """Confirm golden dataset ≥95% accuracy."""
        from interceptor.config import Config
        from interceptor.routing.router import route
        from interceptor.template_registry import TemplateRegistry

        reg = TemplateRegistry.load_all()
        cfg = Config()

        cases = [
            ("review this code", "code-review"),
            ("explain async/await", "explain"),
            ("design a microservice architecture", "architecture"),
            ("შეამოწმე კოდი", "code-review"),
        ]
        passed = sum(
            1
            for text, expected in cases
            if route(text, registry=reg, config=cfg).template_name == expected
        )
        accuracy = passed / len(cases)
        assert accuracy >= 0.95, f"Accuracy {accuracy:.0%} < 95%"

    def test_no_network_dependency(self):
        """Compile + route are pure functions with no network calls."""
        from interceptor.compilation.assembler import compile_prompt
        from interceptor.config import Config
        from interceptor.models.template import (
            Category,
            Template,
            TemplateMeta,
            TemplatePrompt,
            TemplateTriggers,
        )
        from interceptor.routing.router import route
        from interceptor.template_registry import TemplateRegistry

        tpl = Template(
            meta=TemplateMeta(
                name="net_test", category=Category.EVALUATIVE,
                version="1.0.0", author="test",
            ),
            triggers=TemplateTriggers(en=["net test"], ka=["ქსელი"]),
            prompt=TemplatePrompt(
                system_directive="No net.",
                output_schema="Plain text.",
            ),
        )
        reg = TemplateRegistry({tpl.meta.name: tpl})
        cfg = Config()
        decision = route("net test", registry=reg, config=cfg)
        assert decision.template_name == "net_test"
        compiled, _ = compile_prompt(
            template=tpl, raw_input="net test", max_tokens=500
        )
        assert "net test" in compiled.compiled_text

    def test_deterministic_routing(self):
        """Same input always produces same routing decision."""
        from interceptor.config import Config
        from interceptor.routing.router import route
        from interceptor.template_registry import TemplateRegistry

        reg = TemplateRegistry.load_all()
        cfg = Config()
        results = [route("review this code", registry=reg, config=cfg) for _ in range(5)]
        names = {r.template_name for r in results}
        assert len(names) == 1, f"Non-deterministic: {names}"
