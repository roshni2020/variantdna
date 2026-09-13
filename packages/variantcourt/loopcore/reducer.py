"""Deterministic reducer: the only code allowed to produce a new EvidenceState.

- Validates claim references and drops claims citing unknown evidence.
- Applies jury decisions (accept / weaken / reject / unchanged).
- Adds and resolves conflicts.
- Replaces criterion proposals with the jury's current view.
- Leaves evidence_items untouched (immutable source evidence).
- Recomputes the state hash and produces a RoundResult.
"""

from __future__ import annotations

from variantcourt.domain import (
    AgentClaim,
    Conflict,
    CrossExamResult,
    EvidenceState,
    JuryDelta,
    RoundResult,
    compute_state_hash,
)


def _validate_claims(
    claims: list[AgentClaim], known: set[str], invalid: list[str]
) -> list[AgentClaim]:
    ok: list[AgentClaim] = []
    for c in claims:
        if not c.evidence_ids or any(eid not in known for eid in c.evidence_ids):
            invalid.append(c.id)
            continue
        ok.append(c)
    return ok


def reduce_state(
    state: EvidenceState,
    jury_delta: JuryDelta,
    cross_exam: CrossExamResult,
    pathogenic_claims: list[AgentClaim],
    benign_claims: list[AgentClaim],
) -> tuple[EvidenceState, RoundResult]:
    previous_hash = state.state_hash or compute_state_hash(state)
    known = state.evidence_ids()
    invalid: list[str] = []
    changes: list[str] = []

    path_claims = _validate_claims(pathogenic_claims, known, invalid)
    ben_claims = _validate_claims(benign_claims, known, invalid)
    for cid in invalid:
        changes.append(f"Dropped {cid}: cites unknown evidence")

    decisions = {d.claim_id: d for d in jury_delta.claim_decisions}
    claim_status = dict(state.claim_status)

    def apply(claims: list[AgentClaim]) -> list[AgentClaim]:
        out: list[AgentClaim] = []
        for c in claims:
            d = decisions.get(c.id)
            if d is None:
                out.append(c)
                continue
            if d.action == "reject":
                claim_status[c.id] = "reject"
                changes.append(f"Rejected {c.id} ({c.proposed_criterion or 'no criterion'})")
                continue
            if d.action == "weaken":
                new_conf = d.new_confidence if d.new_confidence is not None else c.confidence
                if claim_status.get(c.id) != "weaken":
                    changes.append(f"Weakened {c.id} ({c.proposed_criterion or 'no criterion'})")
                claim_status[c.id] = "weaken"
                out.append(c.model_copy(update={"confidence": new_conf}))
                continue
            if d.action == "accept":
                if claim_status.get(c.id) != "accept":
                    changes.append(f"Accepted {c.id} ({c.proposed_criterion or 'no criterion'})")
                claim_status[c.id] = "accept"
            out.append(c)
        return out

    new_path = apply(path_claims)
    new_ben = apply(ben_claims)

    # Conflicts: add new ones by id, resolve requested ones.
    existing = {c.id: c for c in state.conflicts}
    added: list[str] = []
    for conflict in jury_delta.conflicts_to_add:
        prior = existing.get(conflict.id)
        if prior is not None and not prior.resolved:
            continue
        existing[conflict.id] = conflict.model_copy(update={"resolved": False})
        added.append(conflict.id)
        changes.append(f"Conflict {'reopened' if prior else 'added'}: {conflict.conflict_type} [{conflict.severity}]")
    resolved: list[str] = []
    for cid in jury_delta.conflicts_to_resolve:
        c = existing.get(cid)
        if c and not c.resolved:
            existing[cid] = c.model_copy(update={"resolved": True})
            resolved.append(cid)
            changes.append(f"Conflict resolved: {c.conflict_type}")

    # Criterion proposals.
    new_criteria = {cs.code: cs for cs in jury_delta.criterion_updates}
    for code, cs in new_criteria.items():
        old = state.criterion_states.get(code)
        if old is None:
            changes.append(f"{code} proposed ({cs.status})")
        elif old.status != cs.status or abs(old.confidence - cs.confidence) > 1e-9:
            changes.append(f"{code} {old.status} -> {cs.status}")
    for code in state.criterion_states:
        if code not in new_criteria:
            changes.append(f"{code} withdrawn")

    confidence = (
        jury_delta.confidence_score
        if jury_delta.confidence_score is not None
        else state.confidence_score
    )

    new_state = state.model_copy(
        update={
            "pathogenic_claims": new_path,
            "benign_claims": new_ben,
            "claim_status": claim_status,
            "conflicts": list(existing.values()),
            "open_questions": list(cross_exam.open_questions),
            "criterion_states": new_criteria,
            "confidence_score": confidence,
            "round": state.round + 1,
            "converged": False,
        },
        deep=True,
    )
    new_state.state_hash = compute_state_hash(new_state)

    result = RoundResult(
        round_number=new_state.round,
        previous_state_hash=previous_hash,
        new_state_hash=new_state.state_hash,
        changes=changes,
        conflicts_added=added,
        conflicts_resolved=resolved,
        invalid_claim_ids=invalid,
    )
    return new_state, result
