"""Golden test cases — validate end-to-end routing behavior."""

from __future__ import annotations

import pytest

from interceptor.config import Config, load_config
from interceptor.routing.models import RouteMethod, RouteResult, RouteZone
from interceptor.routing.router import ProjectContext, route
from interceptor.template_registry import TemplateRegistry


@pytest.fixture()
def registry() -> TemplateRegistry:
    return TemplateRegistry.load_all()


@pytest.fixture()
def config() -> Config:
    return load_config()


GOLDEN_CASES: list[tuple[str, str | None, set[str], ProjectContext | None]] = [
    # (input_text, expected_template | None, allowed_zones, context)
    # --- EN exact phrases → AUTO_SELECT / CONFIRM ---
    ("review this code", "code-review", {"AUTO_SELECT", "CONFIRM"}, None),
    ("code review", "code-review", {"AUTO_SELECT", "CONFIRM"}, None),
    # --- EN partial / token overlap → CONFIRM ---
    ("check for bugs", "code-review", {"CONFIRM", "SUGGEST"}, None),
    ("audit the auth module", "security-audit", {"CONFIRM", "SUGGEST"}, None),
    ("explain async/await", "explain", {"CONFIRM", "SUGGEST", "AUTO_SELECT"}, None),
    ("what is a closure?", "explain", {"CONFIRM", "SUGGEST"}, None),
    # --- EN constructive → architecture ---
    ("design a microservice architecture", "architecture", {"CONFIRM", "AUTO_SELECT"}, None),
    # "plan the API structure" can land on architecture or task-planning
    # depending on coverage; both are defensible.
    ("plan the API structure", "task-planning", {"CONFIRM", "AUTO_SELECT", "SUGGEST"}, None),
    # --- KA triggers ---
    ("შეამოწმე კოდი", "code-review", {"CONFIRM", "AUTO_SELECT"}, None),
    ("ახსენი async", "explain", {"CONFIRM", "AUTO_SELECT"}, None),
    ("უსაფრთხოება შეამოწმე", "security-audit", {"CONFIRM", "AUTO_SELECT"}, None),
    # --- Fuzzy → SUGGEST ---
    ("securiy audit please", "security-audit", {"SUGGEST"}, None),
    # --- Mixed category → SUGGEST ---
    # Post-Phase-E: "fix the login bug" now resolves to the more specific
    # debugging template (phrase "fix this bug") rather than code-review.
    ("fix the login bug", "debugging", {"SUGGEST", "CONFIRM"}, None),
    # --- PASSTHROUGH ---
    ("check the weather", None, {"PASSTHROUGH"}, None),
    ("send an email", None, {"PASSTHROUGH"}, None),
    ("don't review this code", None, {"PASSTHROUGH"}, None),
    # --- Empty / whitespace ---
    ("", None, {"PASSTHROUGH"}, None),
    ("   ", None, {"PASSTHROUGH"}, None),
    # --- Negation variants ---
    ("skip code review", None, {"PASSTHROUGH"}, None),
    ("do not review my code", None, {"PASSTHROUGH"}, None),
    # --- Smart default (T3) ---
    (
        "qwxyz random unrelated",
        "code-review",
        {"SUGGEST"},
        ProjectContext(file_path="auth.py", file_extension=".py"),
    ),
    (
        "qwxyz random unrelated",
        "security-audit",
        {"SUGGEST"},
        ProjectContext(file_path="config.yaml", file_extension=".yaml"),
    ),
]


@pytest.mark.parametrize(
    "text, expected_tpl, allowed_zones, context",
    GOLDEN_CASES,
    ids=[c[0][:40] or "<empty>" for c in GOLDEN_CASES],
)
def test_golden_case(
    text: str,
    expected_tpl: str | None,
    allowed_zones: set[str],
    context: ProjectContext | None,
    registry: TemplateRegistry,
    config: Config,
) -> None:
    result = route(text, registry, config, context=context)

    assert result.zone.value in allowed_zones, (
        f"Input: {text!r} → zone={result.zone.value} "
        f"(expected one of {allowed_zones}), conf={result.confidence:.3f}"
    )

    if expected_tpl is not None:
        assert result.template_name == expected_tpl, (
            f"Input: {text!r} → tpl={result.template_name!r} "
            f"(expected {expected_tpl!r})"
        )
    else:
        assert result.is_passthrough, (
            f"Input: {text!r} → expected PASSTHROUGH, "
            f"got zone={result.zone.value} tpl={result.template_name}"
        )


def test_golden_accuracy(registry: TemplateRegistry, config: Config) -> None:
    """At least 90% of golden cases must pass."""
    passed = 0
    for text, expected_tpl, allowed_zones, context in GOLDEN_CASES:
        result = route(text, registry, config, context=context)
        zone_ok = result.zone.value in allowed_zones
        tpl_ok = (expected_tpl is None and result.is_passthrough) or (
            result.template_name == expected_tpl
        )
        if zone_ok and tpl_ok:
            passed += 1

    accuracy = passed / len(GOLDEN_CASES)
    assert accuracy >= 0.90, (
        f"Golden accuracy {accuracy:.0%} ({passed}/{len(GOLDEN_CASES)}) < 90%"
    )


# ---------------------------------------------------------------------------
# Additional edge-case golden tests
# ---------------------------------------------------------------------------


class TestAdditionalGolden:
    def test_security_audit_exact(self, registry: TemplateRegistry, config: Config) -> None:
        result = route("security audit", registry, config)
        assert result.template_name == "security-audit"
        assert result.zone in (RouteZone.AUTO_SELECT, RouteZone.CONFIRM)

    def test_find_bugs_exact(self, registry: TemplateRegistry, config: Config) -> None:
        result = route("find bugs", registry, config)
        assert result.template_name == "code-review"
        assert result.zone in (RouteZone.AUTO_SELECT, RouteZone.CONFIRM)

    def test_vulnerability_scan(self, registry: TemplateRegistry, config: Config) -> None:
        result = route("vulnerability scan", registry, config)
        assert result.template_name == "security-audit"

    def test_long_unrelated_text(self, registry: TemplateRegistry, config: Config) -> None:
        result = route(
            "please book a flight from tbilisi to paris next monday afternoon",
            registry,
            config,
        )
        assert result.is_passthrough

    def test_georgian_unrelated(self, registry: TemplateRegistry, config: Config) -> None:
        result = route("ამინდის პროგნოზი ხვალისათვის", registry, config)
        assert result.is_passthrough
