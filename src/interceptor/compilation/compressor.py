"""Deterministic section-aware template compression."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from interceptor.compilation.models import CompressionLevel

if TYPE_CHECKING:
    from interceptor.models.template import Template

# Canonical section keys (order matters for assembly).
SECTION_KEYS = (
    "system_directive",
    "chain_of_thought",
    "output_schema",
    "quality_gates",
    "anti_patterns",
)


def build_template_sections(template: Template) -> dict[str, str]:
    """Extract canonical sections from a Template into normalised strings.

    Empty optional sections are omitted from the result.
    """
    sections: dict[str, str] = {}

    sd = template.prompt.system_directive.strip()
    if sd:
        sections["system_directive"] = sd

    cot = template.prompt.chain_of_thought.strip()
    if cot:
        sections["chain_of_thought"] = cot

    os_ = template.prompt.output_schema.strip()
    if os_:
        sections["output_schema"] = os_

    gates_parts: list[str] = []
    if template.quality_gates.hard:
        gates_parts.append(
            "Hard: " + "; ".join(template.quality_gates.hard)
        )
    if template.quality_gates.soft:
        gates_parts.append(
            "Soft: " + "; ".join(template.quality_gates.soft)
        )
    if gates_parts:
        sections["quality_gates"] = "\n".join(gates_parts)

    if template.anti_patterns:
        sections["anti_patterns"] = "; ".join(template.anti_patterns)

    return sections


# ---------------------------------------------------------------------------
# Compression transforms
# ---------------------------------------------------------------------------

_MULTI_BLANK_RE = re.compile(r"\n{3,}")
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")


def _minify(text: str) -> str:
    """Normalise whitespace: collapse runs, remove excess blank lines."""
    text = _MULTI_SPACE_RE.sub(" ", text)
    text = _MULTI_BLANK_RE.sub("\n\n", text)
    return text.strip()


def _compact_section(text: str) -> str:
    """Shorten headings/boilerplate and inline verbose lists."""
    text = _minify(text)
    # Convert numbered multi-line lists to semicolon-separated inline form.
    lines = text.split("\n")
    items: list[str] = []
    non_list: list[str] = []
    for line in lines:
        m = re.match(r"^\s*\d+\.\s*(.+)", line)
        if m:
            items.append(m.group(1).rstrip("."))
        else:
            if items:
                non_list.append("; ".join(items))
                items = []
            non_list.append(line)
    if items:
        non_list.append("; ".join(items))
    return "\n".join(non_list).strip()


def _aggressive_section(key: str, text: str) -> str | None:
    """Reduce section for AGGRESSIVE level.

    Preserves system_directive and output_schema almost intact.
    Reduces quality_gates, anti_patterns, chain_of_thought.
    """
    if key in ("system_directive", "output_schema"):
        return _minify(text)
    if key == "chain_of_thought":
        # Reduce to numbered skeleton.
        lines = text.strip().split("\n")
        skeleton: list[str] = []
        for line in lines:
            m = re.match(r"^\s*(\d+)\.\s*(.+)", line)
            if m:
                skeleton.append(f"{m.group(1)}. {m.group(2).split('.')[0]}")
        return "; ".join(skeleton) if skeleton else _minify(text)
    if key in ("quality_gates", "anti_patterns"):
        return _compact_section(text)
    return _minify(text)


def _skeleton_section(key: str, text: str) -> str | None:
    """Keep only the bare essentials for SKELETON level."""
    if key == "system_directive":
        # First sentence only.
        sentences = re.split(r"(?<=\.)\s+", text.strip())
        return sentences[0] if sentences else text.strip()
    if key == "output_schema":
        return _minify(text)
    # chain_of_thought, quality_gates, anti_patterns → omitted
    return None


def compress_sections(
    sections: dict[str, str],
    level: CompressionLevel,
) -> tuple[dict[str, str], list[str]]:
    """Return ``(compressed_sections, included_section_names)``.

    Deterministic and level-aware.
    """
    if level == CompressionLevel.NONE:
        included = [k for k in SECTION_KEYS if k in sections]
        return dict(sections), included

    if level == CompressionLevel.MINIFY:
        out = {k: _minify(v) for k, v in sections.items()}
        included = [k for k in SECTION_KEYS if k in out]
        return out, included

    if level == CompressionLevel.COMPACT:
        out = {k: _compact_section(v) for k, v in sections.items()}
        included = [k for k in SECTION_KEYS if k in out]
        return out, included

    if level == CompressionLevel.AGGRESSIVE:
        out: dict[str, str] = {}
        for k, v in sections.items():
            result = _aggressive_section(k, v)
            if result is not None:
                out[k] = result
        included = [k for k in SECTION_KEYS if k in out]
        return out, included

    # SKELETON
    out_skel: dict[str, str] = {}
    for k, v in sections.items():
        result = _skeleton_section(k, v)
        if result is not None:
            out_skel[k] = result
    included = [k for k in SECTION_KEYS if k in out_skel]
    return out_skel, included
