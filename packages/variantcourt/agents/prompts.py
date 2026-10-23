"""Prompts for LLM-backed agents. Agents see structured state only, never chat history."""

from __future__ import annotations

import json

from variantcourt.domain import AgentClaim, CrossExamResult, EvidenceState

DISCLAIMER = (
    "This is a research prototype for variant interpretation. You are not making a clinical "
    "diagnosis and must never state a final classification."
)

CRITERIA_HELP = (
    "Recognized criterion codes (simplified ACMG-style) and the exact thresholds the rule engine applies: "
    "PVS1 (frameshift/stop-gained/splice/start-lost consequence AND metadata.lof_mechanism true), "
    "PS1 (metadata.same_aa_change_pathogenic true), PS3 (evidence_type functional, direction pathogenic), "
    "PM2 (population_frequency with metadata.allele_frequency < 0.0001), "
    "BA1 (allele_frequency > 0.05), BS1 (0.01 < allele_frequency <= 0.05), "
    "BS3 (evidence_type functional, direction benign), BP4 (evidence_type in_silico, direction benign). "
    "Do NOT propose a criterion whose threshold the cited evidence does not meet; the cross-examiner will reject it. "
    "Returning an empty claims list is correct when no evidence supports your side. "
    "PP5 / BP6 (reviewed ClinVar classification, 2+ stars, from a reputable source; research shortcut). "
    "Unreviewed or 0-star ClinVar entries are context only; leave proposed_criterion null for them."
)


def state_digest(state: EvidenceState) -> str:
    items = [
        {
            "id": e.id,
            "source": e.source,
            "type": e.evidence_type,
            "direction": e.direction,
            "confidence": e.confidence,
            "transcript": e.transcript,
            "summary": e.summary,
            "metadata": e.metadata,
        }
        for e in state.evidence_items
    ]
    return json.dumps(
        {
            "variant": state.variant.model_dump(),
            "disease_context": state.disease_context.model_dump() if state.disease_context else None,
            "round": state.round,
            "evidence": items,
            "claim_status_from_previous_rounds": state.claim_status,
            "why_claims_were_rejected_or_weakened": [
                {"claim_ids": c.affected_claim_ids, "type": c.conflict_type, "reason": c.description}
                for c in state.conflicts
            ],
            "unresolved_conflicts": [c.model_dump() for c in state.unresolved_conflicts()],
            "criterion_states": {k: v.model_dump() for k, v in state.criterion_states.items()},
            "open_questions": state.open_questions,
        },
        indent=1,
    )


def counsel_system(side: str) -> str:
    goal = (
        "Build the strongest evidence-supported case that this variant may contribute to disease."
        if side == "pathogenic"
        else "Build the strongest evidence-supported case that this variant is benign. "
        "Absence of evidence is NOT benign evidence."
    )
    return (
        f"You are {side.title()} Counsel in VariantCourt. {DISCLAIMER}\n{goal}\n"
        "Rules:\n"
        "- Cite ONLY evidence ids that appear in the evidence list. Never invent evidence.\n"
        "- Do not cite evidence annotated on a transcript different from the case transcript.\n"
        "- Do not re-propose an argument that was rejected in a previous round, even reworded or with different "
        "evidence of the same kind; read why_claims_were_rejected_or_weakened. Lower confidence for weakened ones.\n"
        "- Stability matters: if nothing in the evidence changed, repeat your surviving claims verbatim.\n"
        "- One criterion per claim; do not propose the same criterion twice.\n"
        "- Confidence must not exceed the confidence of the strongest evidence you cite.\n"
        f"- {CRITERIA_HELP}\n"
        f"- Set agent to '{side}_counsel'. Claim ids must be unique strings starting with 'claim_'.\n"
        "- To answer an opposing claim directly, set rebuts to that claim's id; otherwise leave rebuts null."
    )


def counsel_user(state: EvidenceState, opponent: list[AgentClaim] | None = None) -> str:
    text = "Shared evidence state:\n" + state_digest(state)
    if opponent:
        text += "\n\nOpposing counsel's claims this round (you may answer one directly by setting rebuts to its id; " \
                "a rebuttal must still cite evidence and may not restate your own earlier claim):\n" + json.dumps(
            [{"id": c.id, "criterion": c.proposed_criterion, "claim": c.claim, "evidence_ids": c.evidence_ids} for c in opponent], indent=1
        )
    return text + "\nReturn your claims."


JURY_SYSTEM = (
    f"You are the Jury in VariantCourt. {DISCLAIMER}\n"
    "You receive the claims of both counsels and an independent cross-examination. Decide, per claim, whether to "
    "accept, weaken, reject or leave unchanged; propose criterion states for surviving claims; list which existing "
    "conflict ids are now resolved; and give a confidence_score in [0,1] where 1 means the pathogenic side is "
    "fully dominant and 0 means the benign side is. Rejected claims by the cross-examiner should normally be "
    "rejected. You never issue a classification. Reference only claim ids and conflict ids you were given."
)


def jury_user(
    state: EvidenceState,
    pathogenic_claims: list[AgentClaim],
    benign_claims: list[AgentClaim],
    cross_exam: CrossExamResult,
) -> str:
    return json.dumps(
        {
            "state": json.loads(state_digest(state)),
            "pathogenic_claims": [c.model_dump() for c in pathogenic_claims],
            "benign_claims": [c.model_dump() for c in benign_claims],
            "cross_examination": cross_exam.model_dump(),
        },
        indent=1,
    )
