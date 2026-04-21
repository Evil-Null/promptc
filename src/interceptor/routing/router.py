"""Template router — 4-zone resolution with multi-layer scoring."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from interceptor.config import Config
from interceptor.models.template import Category, Template
from interceptor.routing.index import build_trigger_index, normalize_phrase, tokenize
from interceptor.routing.models import RouteMethod, RouteResult, RouteZone
from interceptor.routing.scoring import score_template
from interceptor.template_registry import TemplateRegistry

# ---------------------------------------------------------------------------
# ProjectContext — plain dataclass (NOT Pydantic), expanded later
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProjectContext:
    """Lightweight context about the user's project environment."""

    file_path: str | None = None
    file_extension: str | None = None
    language: str | None = None


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_NEGATION_PREFIXES = ("don't ", "dont ", "do not ", "no ", "skip ")

_STOP_WORDS = frozenset({
    "a", "an", "the", "this", "that", "my", "your", "me", "i",
    "for", "in", "on", "of", "to", "is", "it", "its",
    "and", "or", "do", "does", "did",
    "please", "just", "some", "here", "there",
})

# Phase B3: generic nouns that contribute diluted weight when matched alone.
# Present in trigger phrases but too broad to carry routing confidence on
# their own (e.g. "fix error in system" must not win against "system design").
_GENERIC_NOUNS = frozenset({
    "system", "code", "project", "file", "files", "thing", "things",
    "app", "application", "service", "module", "function", "class",
})
_GENERIC_WEIGHT: float = 0.5

# Phase B2: unigram-only matches (no phrase evidence, single token overlap)
# cannot exceed SUGGEST. Max confidence for such matches.
_UNIGRAM_ONLY_CAP: float = 0.54

# Phase B1: category-only matches (no trigger or token evidence) cannot
# exceed SUGGEST zone. Max confidence for pure category-affinity wins.
_CATEGORY_ONLY_CAP: float = 0.54

_STRENGTH_MULT: dict[str | None, float] = {
    "STRONG": 1.0,
    "MEDIUM": 0.92,
    "WEAK": 0.75,
    None: 0.92,
}

_CATEGORY_KEYWORDS: dict[str, Category] = {
    # English
    "what": Category.COMMUNICATIVE,
    "how": Category.COMMUNICATIVE,
    "why": Category.COMMUNICATIVE,
    "explain": Category.COMMUNICATIVE,
    "describe": Category.COMMUNICATIVE,
    "understand": Category.COMMUNICATIVE,
    "review": Category.EVALUATIVE,
    "audit": Category.EVALUATIVE,
    "test": Category.EVALUATIVE,
    "verify": Category.EVALUATIVE,
    "bugs": Category.EVALUATIVE,
    "bug": Category.EVALUATIVE,
    "analyze": Category.EVALUATIVE,
    "vulnerability": Category.EVALUATIVE,
    "security": Category.EVALUATIVE,
    "design": Category.CONSTRUCTIVE,
    "architect": Category.CONSTRUCTIVE,
    "architecture": Category.CONSTRUCTIVE,
    "plan": Category.CONSTRUCTIVE,
    "structure": Category.CONSTRUCTIVE,
    "build": Category.CONSTRUCTIVE,
    "create": Category.CONSTRUCTIVE,
    "scale": Category.CONSTRUCTIVE,
    "api": Category.CONSTRUCTIVE,
    "fix": Category.TRANSFORMATIVE,
    "refactor": Category.TRANSFORMATIVE,
    "optimize": Category.TRANSFORMATIVE,
    "improve": Category.TRANSFORMATIVE,
    "migrate": Category.TRANSFORMATIVE,
    "convert": Category.TRANSFORMATIVE,
    # Georgian (Phase C — bilingual parity)
    "ახსენი": Category.COMMUNICATIVE,
    "ამიხსენი": Category.COMMUNICATIVE,
    "რას": Category.COMMUNICATIVE,
    "როგორ": Category.COMMUNICATIVE,
    "რატომ": Category.COMMUNICATIVE,
    "რევიუ": Category.EVALUATIVE,
    "შეამოწმე": Category.EVALUATIVE,
    "შემოწმება": Category.EVALUATIVE,
    "აუდიტი": Category.EVALUATIVE,
    "უსაფრთხოება": Category.EVALUATIVE,
    "დიზაინი": Category.CONSTRUCTIVE,
    "არქიტექტურა": Category.CONSTRUCTIVE,
    "შექმენი": Category.CONSTRUCTIVE,
    "დაგეგმე": Category.CONSTRUCTIVE,
    "გაასწორე": Category.TRANSFORMATIVE,
    "გადააკეთე": Category.TRANSFORMATIVE,
    "გააუმჯობესე": Category.TRANSFORMATIVE,
}

_FILE_TYPE_DEFAULTS: dict[str, str] = {
    ".py": "code-review",
    ".js": "code-review",
    ".ts": "code-review",
    ".tsx": "code-review",
    ".jsx": "code-review",
    ".java": "code-review",
    ".go": "code-review",
    ".rs": "code-review",
    ".rb": "code-review",
    ".c": "code-review",
    ".cpp": "code-review",
    ".cs": "code-review",
    ".kt": "code-review",
    ".swift": "code-review",
    ".yaml": "security-audit",
    ".yml": "security-audit",
    ".tf": "security-audit",
    ".md": "explain",
    ".txt": "explain",
    ".rst": "explain",
}


# ---------------------------------------------------------------------------
# Levenshtein — inline DP, zero external deps
# ---------------------------------------------------------------------------


def levenshtein(a: str, b: str) -> int:
    """Compute Levenshtein edit distance between *a* and *b*."""
    if len(a) < len(b):
        return levenshtein(b, a)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for ca in a:
        curr = [prev[0] + 1]
        for j, cb in enumerate(b):
            cost = 0 if ca == cb else 1
            curr.append(min(curr[j] + 1, prev[j + 1] + 1, prev[j] + cost))
        prev = curr
    return prev[-1]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def route(
    text: str,
    registry: TemplateRegistry,
    config: Config,
    *,
    context: ProjectContext | None = None,
    explicit_template: str | None = None,
) -> RouteResult:
    """Route *text* to the best-matching template (pure function).

    Parameters
    ----------
    text:
        Raw user input.
    registry:
        Loaded template registry.
    config:
        Application config (zone thresholds, weights, etc.).
    context:
        Optional project context (file path, extension).
    explicit_template:
        If the user explicitly named a template (``--template``).
    """
    if explicit_template is not None:
        return _resolve_explicit(explicit_template, registry)

    tokens = tokenize(text)

    if not tokens:
        return RouteResult()

    if _is_negated(text):
        return RouteResult()

    templates = registry.all_templates()
    if not templates:
        return RouteResult()

    index = build_trigger_index(templates)
    rcfg = config.routing

    scores: dict[str, float] = {}
    fuzzy_flags: dict[str, bool] = {}
    phrase_flags: dict[str, bool] = {}
    cat_only_flags: dict[str, bool] = {}
    evidence_counts: dict[str, int] = {}

    for t in templates:
        exact = score_template(text, t, index, rcfg)
        tok_conf, has_fuzzy, phrase_matched, evidence = _token_match_confidence(tokens, t)
        cat_conf = _category_affinity(tokens, t.meta.category, t.triggers.strength)

        combined = max(exact, tok_conf) if has_fuzzy else max(exact, tok_conf, cat_conf)

        # Phase B: +0.05 synergy bonus only when real phrase evidence exists —
        # prevents unigram + category affinity from reaching CONFIRM.
        if not has_fuzzy and tok_conf > 0 and cat_conf > 0 and phrase_matched:
            combined = min(combined + 0.05, 0.95)

        # Phase B1: pure category-affinity wins cap at SUGGEST zone.
        cat_only = (exact == 0.0 and tok_conf == 0.0 and cat_conf > 0.0)
        if cat_only:
            combined = min(combined, _CATEGORY_ONLY_CAP)

        # Phase B2: if no multi-token phrase evidence at all, cap at SUGGEST.
        # Applies to unigram-only + category-affinity combinations.
        if not phrase_matched and exact == 0.0:
            combined = min(combined, _CATEGORY_ONLY_CAP)

        if combined > 0:
            scores[t.meta.name] = combined
            fuzzy_flags[t.meta.name] = has_fuzzy
            phrase_flags[t.meta.name] = phrase_matched
            cat_only_flags[t.meta.name] = cat_only
            evidence_counts[t.meta.name] = evidence

    if not scores:
        return _fallback_cascade(tokens, templates, registry, context)

    ranked = sorted(
        scores.items(),
        key=lambda x: (x[1], evidence_counts.get(x[0], 0)),
        reverse=True,
    )
    top_name, top_score = ranked[0]
    runner_up = ranked[1] if len(ranked) > 1 else None

    if top_score < 0.30:
        fb = _fallback_cascade(tokens, templates, registry, context)
        if fb.confidence > top_score:
            return fb

    if fuzzy_flags.get(top_name, False):
        capped = min(top_score, 0.54)
        return RouteResult(
            template_name=top_name,
            zone=RouteZone.SUGGEST,
            method=RouteMethod.FUZZY_MATCH,
            confidence=capped,
            runner_up=runner_up[0] if runner_up else None,
            scores=dict(ranked),
        )

    zone = _classify_zone(top_score)
    method = RouteMethod.SCORE_WINNER

    if runner_up and runner_up[1] > 0:
        gap = top_score - runner_up[1]
        if gap < rcfg.clarity_gap:
            top_tpl = registry.get(top_name)
            run_tpl = registry.get(runner_up[0])
            if top_tpl and run_tpl:
                if top_tpl.meta.category == run_tpl.meta.category:
                    method = RouteMethod.USER_CHOICE
                else:
                    method = RouteMethod.CHAIN_SUGGESTED
                if zone == RouteZone.AUTO_SELECT:
                    zone = RouteZone.CONFIRM

    return RouteResult(
        template_name=top_name,
        zone=zone,
        method=method,
        confidence=top_score,
        runner_up=runner_up[0] if runner_up else None,
        scores=dict(ranked),
    )


# ---------------------------------------------------------------------------
# Zone helpers
# ---------------------------------------------------------------------------


def _classify_zone(score: float) -> RouteZone:
    if score >= 0.80:
        return RouteZone.AUTO_SELECT
    if score >= 0.55:
        return RouteZone.CONFIRM
    if score >= 0.30:
        return RouteZone.SUGGEST
    return RouteZone.PASSTHROUGH


def _is_negated(text: str) -> bool:
    lower = text.strip().lower()
    return any(lower.startswith(p) for p in _NEGATION_PREFIXES)


# ---------------------------------------------------------------------------
# Explicit template resolution
# ---------------------------------------------------------------------------


def _resolve_explicit(name: str, registry: TemplateRegistry) -> RouteResult:
    t = registry.get(name)
    if t is not None:
        return RouteResult(
            template_name=name,
            zone=RouteZone.AUTO_SELECT,
            method=RouteMethod.EXPLICIT,
            confidence=1.0,
        )
    best_name: str | None = None
    best_dist = 999
    for t in registry.all_templates():
        d = levenshtein(name.lower(), t.meta.name.lower())
        if d < best_dist:
            best_dist = d
            best_name = t.meta.name
    if best_name is not None and best_dist <= 2:
        return RouteResult(
            template_name=best_name,
            zone=RouteZone.SUGGEST,
            method=RouteMethod.FUZZY_MATCH,
            confidence=0.50,
        )
    msg = f"Unknown template: {name!r}"
    raise ValueError(msg)


# ---------------------------------------------------------------------------
# Token-level matching (Layer 2)
# ---------------------------------------------------------------------------


def _token_match_confidence(
    tokens: list[str],
    template: Template,
) -> tuple[float, bool, bool, int]:
    """Return ``(confidence, has_fuzzy, phrase_matched, evidence_count)``.

    ``evidence_count`` is the number of unique significant input tokens
    that exact-matched any trigger phrase — used as a tiebreaker when two
    templates hit the 0.95 cap with different evidence richness.
    """
    token_set = set(tokens)
    significant_input = token_set - _STOP_WORDS
    if not significant_input:
        return 0.0, False, False, 0

    phrases: list[str] = []
    for p in template.triggers.en + template.triggers.ka:
        norm = normalize_phrase(p)
        if norm:
            phrases.append(norm)
    if not phrases:
        return 0.0, False, False, 0

    matched_exact: set[str] = set()
    best_overlap = 0.0
    best_exact_ratio = 0.0
    has_fuzzy = False
    phrase_matched = False

    for phrase in phrases:
        ptokens = phrase.split()
        ptokens_set = set(ptokens)
        significant_phrase = ptokens_set - _STOP_WORDS
        if not significant_phrase:
            continue

        exact = significant_input & significant_phrase

        # Phase B3: dilute generic-noun-only contributions.
        weighted_exact = sum(
            _GENERIC_WEIGHT if tok in _GENERIC_NOUNS else 1.0
            for tok in exact
        )

        fuzzy_count = 0
        for it in significant_input - exact:
            if len(it) < 4:
                continue
            for pt in significant_phrase - exact:
                if len(pt) < 4:
                    continue
                if levenshtein(it, pt) <= 2:
                    fuzzy_count += 1
                    has_fuzzy = True
                    break

        # Count multi-token phrase evidence: ≥2 significant overlaps
        # (exact non-generic + fuzzy) against a single phrase.
        non_generic_exact = {tok for tok in exact if tok not in _GENERIC_NOUNS}
        if len(non_generic_exact) + fuzzy_count >= 2:
            phrase_matched = True

        exact_ratio = len(exact) / len(significant_phrase)
        best_exact_ratio = max(best_exact_ratio, exact_ratio)

        total = weighted_exact + fuzzy_count * 0.5
        if total > 0:
            ratio = total / len(ptokens)
            matched_exact.update(exact)
            best_overlap = max(best_overlap, ratio)

    fuzzy_is_relevant = has_fuzzy and best_exact_ratio < 0.80

    unique_count = len(matched_exact)
    if unique_count < 2 and best_overlap < 0.50:
        if fuzzy_is_relevant:
            return 0.0, True, False, unique_count
        return 0.0, False, False, unique_count

    name_tokens = set(template.meta.name.lower().replace("-", " ").split())
    all_name_present = bool(name_tokens) and name_tokens <= token_set

    signal = best_overlap
    if unique_count > 1:
        signal += 0.10 * min(unique_count - 1, 3)
    if all_name_present:
        signal = max(signal, 0.70)

    # Broaden phrase evidence: 2+ distinct exact overlaps or full template
    # name present in input counts as real multi-signal evidence.
    if unique_count >= 2 or all_name_present:
        phrase_matched = True

    mult = _STRENGTH_MULT.get(template.triggers.strength, 0.92)
    raw = min(signal * mult, 0.95)

    # Phase B2: unigram-only match (no multi-token phrase evidence) caps at
    # SUGGEST zone — prevents single common word from reaching CONFIRM.
    if not phrase_matched and unique_count <= 1 and not all_name_present:
        raw = min(raw, _UNIGRAM_ONLY_CAP)

    return raw, fuzzy_is_relevant, phrase_matched, unique_count


# ---------------------------------------------------------------------------
# Category affinity (Layer 3)
# ---------------------------------------------------------------------------


def _category_affinity(
    tokens: list[str],
    target: Category,
    strength: str | None,
) -> float:
    """Score based on keyword → category mapping with focus penalty."""
    all_hits: Counter[Category] = Counter()
    for t in tokens:
        cat = _CATEGORY_KEYWORDS.get(t)
        if cat is not None:
            all_hits[cat] += 1

    target_hits = all_hits.get(target, 0)
    if target_hits == 0:
        return 0.0

    total = sum(all_hits.values())
    focus = target_hits / total
    base = min(0.50 + 0.12 * target_hits, 0.80)
    base *= focus

    mult = _STRENGTH_MULT.get(strength, 0.92)
    return base * mult


# ---------------------------------------------------------------------------
# Fallback cascade  T1 → T4
# ---------------------------------------------------------------------------


def _fallback_cascade(
    tokens: list[str],
    templates: list[Template],
    registry: TemplateRegistry,
    context: ProjectContext | None,
) -> RouteResult:
    result = _fuzzy_trigger_fallback(tokens, templates)
    if result is not None:
        return result

    result = _smart_default(context, registry)
    if result is not None:
        return result

    return RouteResult()


def _fuzzy_trigger_fallback(
    tokens: list[str],
    templates: list[Template],
) -> RouteResult | None:
    """T1: Levenshtein match of input n-grams against trigger phrases."""
    ngrams: list[str] = []
    n = len(tokens)
    for length in range(min(n, 4), 0, -1):
        for start in range(n - length + 1):
            ngrams.append(" ".join(tokens[start : start + length]))

    best_tpl: str | None = None
    best_dist = 999
    for t in templates:
        for phrase in t.triggers.en + t.triggers.ka:
            norm = phrase.strip().lower()
            if len(norm) < 4:
                continue
            for ng in ngrams:
                if len(ng) < 4:
                    continue
                d = levenshtein(ng, norm)
                max_len = max(len(ng), len(norm))
                if d <= 2 and d / max_len <= 0.15 and d < best_dist:
                    best_dist = d
                    best_tpl = t.meta.name

    if best_tpl is not None:
        return RouteResult(
            template_name=best_tpl,
            zone=RouteZone.SUGGEST,
            method=RouteMethod.FUZZY_MATCH,
            confidence=0.40,
        )
    return None


def _smart_default(
    context: ProjectContext | None,
    registry: TemplateRegistry,
) -> RouteResult | None:
    """T3: File extension → default template."""
    if context is None:
        return None

    tpl_name: str | None = None
    if context.file_extension:
        tpl_name = _FILE_TYPE_DEFAULTS.get(context.file_extension.lower())

    if tpl_name is None and context.file_path:
        if "dockerfile" in context.file_path.lower():
            tpl_name = "security-audit"

    if tpl_name is None or registry.get(tpl_name) is None:
        return None

    return RouteResult(
        template_name=tpl_name,
        zone=RouteZone.SUGGEST,
        method=RouteMethod.SMART_DEFAULT,
        confidence=0.35,
    )
