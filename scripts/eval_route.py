"""Phase-A repro harness: evaluate routing against a pinned corpus.

Usage:
    PYTHONPATH=src python scripts/eval_route.py [--snapshot out.json] [--builtin-only]

Builtin-only mode skips custom templates and plugins to isolate core behavior.
Emits a snapshot (JSON) and a concise accuracy report.

Design notes
------------
- No network, no LLM calls — pure routing math.
- Deterministic: sorts inputs by id, emits stable JSON keys.
- Non-zero exit if accuracy regresses below baseline threshold.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from interceptor.config import load_config
from interceptor.routing.models import RouteZone
from interceptor.routing.router import route
from interceptor.template_registry import TemplateRegistry

_ZONE_ORDER: dict[str, int] = {
    "PASSTHROUGH": 0,
    "SUGGEST": 1,
    "CONFIRM": 2,
    "AUTO_SELECT": 3,
}


@dataclass(frozen=True)
class Case:
    id: str
    text: str
    expected_template: str | None
    expected_zone_min: str
    lang: str


@dataclass
class Outcome:
    id: str
    text: str
    lang: str
    actual_template: str | None
    actual_zone: str
    confidence: float
    method: str | None
    runner_up: str | None
    top_scores: dict[str, float]
    expected_template: str | None
    expected_zone_min: str
    verdict: str  # pass | fail_template | fail_zone


def _load_corpus(path: Path) -> list[Case]:
    cases: list[Case] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        rec = json.loads(line)
        cases.append(Case(
            id=rec["id"],
            text=rec["text"],
            expected_template=rec.get("expected_template"),
            expected_zone_min=rec["expected_zone_min"],
            lang=rec.get("lang", "en"),
        ))
    return cases


def _grade(case: Case, actual_template: str | None, actual_zone: str) -> str:
    if case.expected_template is None:
        return "pass" if actual_template is None else "fail_template"
    if actual_template != case.expected_template:
        return "fail_template"
    if _ZONE_ORDER[actual_zone] < _ZONE_ORDER[case.expected_zone_min]:
        return "fail_zone"
    return "pass"


def _build_registry(*, builtin_only: bool) -> TemplateRegistry:
    if not builtin_only:
        return TemplateRegistry.load_all()
    from interceptor.constants import TEMPLATES_BUILTIN_DIR
    from interceptor.template_loader import load_template
    templates = {}
    for toml_file in sorted(TEMPLATES_BUILTIN_DIR.glob("*.toml")):
        tpl = load_template(toml_file)
        if tpl is not None:
            templates[tpl.meta.name] = tpl
    return TemplateRegistry(templates)


def run(corpus_path: Path, *, builtin_only: bool) -> list[Outcome]:
    cases = _load_corpus(corpus_path)
    config = load_config()
    registry = _build_registry(builtin_only=builtin_only)

    outcomes: list[Outcome] = []
    for case in sorted(cases, key=lambda c: c.id):
        result = route(case.text, registry, config)
        actual_zone = result.zone.value if result.zone else RouteZone.PASSTHROUGH.value
        outcomes.append(Outcome(
            id=case.id,
            text=case.text,
            lang=case.lang,
            actual_template=result.template_name,
            actual_zone=actual_zone,
            confidence=round(result.confidence, 4),
            method=result.method.value if result.method else None,
            runner_up=result.runner_up,
            top_scores={k: round(v, 4) for k, v in sorted(
                result.scores.items(), key=lambda x: x[1], reverse=True
            )[:3]},
            expected_template=case.expected_template,
            expected_zone_min=case.expected_zone_min,
            verdict=_grade(case, result.template_name, actual_zone),
        ))
    return outcomes


def _report(outcomes: list[Outcome]) -> tuple[int, int, int]:
    passed = sum(1 for o in outcomes if o.verdict == "pass")
    fail_tpl = sum(1 for o in outcomes if o.verdict == "fail_template")
    fail_zone = sum(1 for o in outcomes if o.verdict == "fail_zone")
    total = len(outcomes)

    print(f"\n=== Routing Eval Report ===")
    print(f"Total: {total}  Pass: {passed}  Fail-template: {fail_tpl}  Fail-zone: {fail_zone}")
    print(f"Accuracy: {passed / total:.1%}\n")

    for o in outcomes:
        if o.verdict == "pass":
            continue
        exp = o.expected_template or "PASSTHROUGH"
        act = o.actual_template or "PASSTHROUGH"
        print(f"  [{o.verdict:14}] {o.id:14} expected={exp:20} actual={act:20} conf={o.confidence}  | {o.text}")
    return passed, fail_tpl, fail_zone


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=Path, default=Path("tests/eval/corpus.jsonl"))
    ap.add_argument("--snapshot", type=Path, default=None,
                    help="Write outcomes as JSON to this path")
    ap.add_argument("--builtin-only", action="store_true", default=True,
                    help="Isolate builtin templates (default: true)")
    ap.add_argument("--include-custom", dest="builtin_only", action="store_false",
                    help="Include custom templates and plugins")
    args = ap.parse_args()

    if not args.corpus.exists():
        print(f"Corpus not found: {args.corpus}", file=sys.stderr)
        return 2

    outcomes = run(args.corpus, builtin_only=args.builtin_only)
    passed, fail_tpl, fail_zone = _report(outcomes)

    if args.snapshot:
        args.snapshot.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "corpus": str(args.corpus),
            "builtin_only": args.builtin_only,
            "totals": {
                "total": len(outcomes),
                "pass": passed,
                "fail_template": fail_tpl,
                "fail_zone": fail_zone,
            },
            "outcomes": [asdict(o) for o in outcomes],
        }
        args.snapshot.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nSnapshot written to {args.snapshot}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
