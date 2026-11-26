"""Versioned prompts. Changing any text here bumps ``PROMPT_VERSION`` (recorded with every output)."""

from __future__ import annotations

from via_ai.context import ProjectContext
from via_ai.verification import context_json

PROMPT_VERSION = "2026-11-26.1"

SYSTEM = """You are VIA's PCB design assistant, helping a hardware engineer understand a real board.

Rules:
- Use only the design data in the CONTEXT (JSON). Never invent components, nets, layers, findings,
  measurements or component specifications. If the context doesn't contain what's needed, say so in
  `uncertainties` instead of guessing.
- Cite what you rely on: every component reference, net name, layer and finding id you depend on goes
  in `references` (or `evidence_finding_ids`), spelled exactly as in the context.
- Every number you state goes in `numbers_used` with the context field it came from. Don't compute new
  measurements; you may quote the analysis findings' evidence.
- Findings come from deterministic checks or KiCad's DRC, with a `verification` level. Treat
  `verified` findings as facts and `heuristic` ones as indications. Your own ideas are hypotheses:
  label them as such and say how to validate them.
- Lengths are millimetres. Be concise and practical; write for an engineer."""


def explain_messages(context: ProjectContext, question: str) -> tuple[str, str]:
    focus = f" The question is about {context.focus.kind} {context.focus.id}." if context.focus else ""
    user = f"QUESTION: {question.strip()}{focus}\n\nCONTEXT:\n{context_json(context)}"
    return SYSTEM, user


def review_messages(context: ProjectContext) -> tuple[str, str]:
    user = (
        "Write a structured design review of this board covering layout, routing, placement, manufacturability, "
        "electrical concerns and design-rule compliance. In each section list the ids of context findings that "
        "belong there, then any engineering hypotheses (clearly not verified). Finish with up to 10 "
        "recommendations, each tied to evidence finding ids where possible.\n\n"
        f"CONTEXT:\n{context_json(context)}"
    )
    return SYSTEM, user
