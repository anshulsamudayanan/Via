"""Checks a model's structured output against the context it was given.

An output is rejected (never shown as an answer) when it:

* cites a component, net, layer or finding that isn't in the context;
* names a reference designator in its text that isn't in the design;
* uses a number (``numbers_used``) that doesn't appear anywhere in the context.

This catches the common failure modes of language models on engineering data (invented parts,
nets or measurements). It cannot prove the reasoning is right: outputs stay labelled as
unverified AI suggestions.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable

from pydantic import BaseModel, Field

from via_ai.context import ProjectContext
from via_ai.schemas import DesignReview, Explanation, NumberUsed, Recommendation, Reference

#: Common reference designator prefixes; text mentions of these must exist in the design.
_REFDES = re.compile(r"\b(?:R|C|L|U|J|P|Q|D|Y|X|K|F|T|SW|TP|FB|IC|CN|LED|BT|RV|JP)\d{1,4}[A-Z]?\b")
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?(?:[eE]-?\d+)?")


class VerificationReport(BaseModel):
    ok: bool
    unknown_references: list[str] = Field(default_factory=list)
    unknown_mentions: list[str] = Field(default_factory=list)
    unsupported_numbers: list[str] = Field(default_factory=list)

    @property
    def problems(self) -> list[str]:
        out = [f"Reference not in the design: {r}" for r in self.unknown_references]
        out += [f"Mentioned part not in the design: {m}" for m in self.unknown_mentions]
        out += [f"Number not found in the design data: {n}" for n in self.unsupported_numbers]
        return out


def _known(context: ProjectContext) -> dict[str, set[str]]:
    comps = {c.reference for c in context.components}
    nets = set(context.net_names)
    for f in context.findings:
        comps.update(f.components)
        nets.update(f.nets)
    for r in context.component_records:
        comps.update(r.references)
    if context.focus is not None:
        if context.focus.kind == "component":
            comps.add(context.focus.id)
        elif context.focus.kind == "net":
            nets.add(context.focus.id)
    return {
        "component": comps,
        "net": nets,
        "finding": {f.id for f in context.findings},
        "layer": {layer.name for layer in context.layers},
    }


def context_numbers(context: ProjectContext) -> list[float]:
    return [float(m) for m in _NUMBER.findall(context.model_dump_json())]


def _number_supported(n: NumberUsed, numbers: list[float]) -> bool:
    return any(abs(n.value - v) <= max(1e-6, 1e-3 * abs(v)) for v in numbers)


def _walk(output: BaseModel) -> tuple[list[Reference], list[str], list[NumberUsed], list[str]]:
    refs: list[Reference] = []
    finding_ids: list[str] = []
    numbers: list[NumberUsed] = []
    texts: list[str] = []

    def rec(r: Recommendation) -> None:
        refs.extend(r.references)
        finding_ids.extend(r.evidence_finding_ids)
        numbers.extend(r.numbers_used)
        texts.extend([r.problem, r.proposed_change, r.rationale, r.uncertainty, *r.expected_benefits, *r.trade_offs])

    if isinstance(output, Explanation):
        refs.extend(output.references)
        numbers.extend(output.numbers_used)
        texts.extend([output.answer, *output.key_points])
    elif isinstance(output, DesignReview):
        texts.append(output.summary)
        for section in output.sections:
            finding_ids.extend(section.verified_findings)
            for h in section.hypotheses:
                refs.extend(h.references)
                texts.extend([h.statement, h.rationale])
        for r in output.recommendations:
            rec(r)
    elif isinstance(output, Recommendation):
        rec(output)
    return refs, finding_ids, numbers, texts


def verify(output: BaseModel, context: ProjectContext) -> VerificationReport:
    known = _known(context)
    refs, finding_ids, numbers, texts = _walk(output)
    unknown = [f"{r.kind}:{r.id}" for r in refs if r.id not in known.get(r.kind, set())]
    unknown += [f"finding:{fid}" for fid in finding_ids if fid not in known["finding"]]
    mentions = sorted({m for t in texts for m in _REFDES.findall(t)} - known["component"])
    ctx_numbers = context_numbers(context)
    unsupported = [
        f"{n.value:g}{(' ' + n.unit) if n.unit else ''} ({n.source})"
        for n in numbers
        if not _number_supported(n, ctx_numbers)
    ]
    return VerificationReport(
        ok=not (unknown or mentions or unsupported),
        unknown_references=_dedupe(unknown),
        unknown_mentions=mentions,
        unsupported_numbers=unsupported,
    )


def _dedupe(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(items))


def context_json(context: ProjectContext) -> str:
    """Canonical JSON of the context (what the model sees; hashed for audit)."""
    return json.dumps(context.model_dump(mode="json", exclude_none=True), sort_keys=True, separators=(",", ":"))
