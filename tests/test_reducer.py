import pytest

from variantcourt.domain import (
    AgentClaim,
    ClaimDecision,
    Conflict,
    CriterionState,
    CrossExamResult,
    EvidenceItem,
    EvidenceState,
    JuryDelta,
    NormalizedVariant,
)
from variantcourt.loopcore import has_converged, reduce_state


def _state() -> EvidenceState:
    return EvidenceState(
        variant=NormalizedVariant(input="v", transcript="NM_1.1"),
        evidence_items=[
            EvidenceItem(id="ev_a", source="s", evidence_type="t", summary="a", direction="pathogenic", confidence=0.8),
        ],
    )


def _claim(cid: str, eids: list[str], criterion="PM2", agent="pathogenic_counsel") -> AgentClaim:
    return AgentClaim(id=cid, agent=agent, claim="c", evidence_ids=eids, proposed_criterion=criterion, confidence=0.7)


def test_reducer_drops_claims_with_unknown_evidence():
    state = _state()
    good, bad = _claim("c1", ["ev_a"]), _claim("c2", ["ev_missing"])
    delta = JuryDelta(claim_decisions=[ClaimDecision(claim_id="c1", action="accept", rationale="ok")])
    new, result = reduce_state(state, delta, CrossExamResult(), [good, bad], [])
    assert [c.id for c in new.pathogenic_claims] == ["c1"]
    assert result.invalid_claim_ids == ["c2"]
    assert new.round == 1
    assert new.state_hash != state.state_hash or state.state_hash == ""


def test_reducer_applies_decisions_and_preserves_evidence():
    state = _state()
    original_evidence = [e.model_copy(deep=True) for e in state.evidence_items]
    claims = [_claim("c1", ["ev_a"]), _claim("c2", ["ev_a"], criterion="PS3")]
    delta = JuryDelta(
        claim_decisions=[
            ClaimDecision(claim_id="c1", action="weaken", rationale="w", new_confidence=0.2),
            ClaimDecision(claim_id="c2", action="reject", rationale="r"),
        ],
        conflicts_to_add=[Conflict(id="cf1", conflict_type="x", description="d", affected_claim_ids=["c2"], severity="high")],
        criterion_updates=[CriterionState(code="PM2", status="WEAKENED", confidence=0.2)],
        confidence_score=0.4,
    )
    new, result = reduce_state(state, delta, CrossExamResult(), claims, [])
    assert [c.id for c in new.pathogenic_claims] == ["c1"]
    assert new.pathogenic_claims[0].confidence == 0.2
    assert new.claim_status == {"c1": "weaken", "c2": "reject"}
    assert result.conflicts_added == ["cf1"]
    assert new.criterion_states["PM2"].status == "WEAKENED"
    assert new.confidence_score == 0.4
    assert new.evidence_items == original_evidence
    assert state.round == 0 and state.pathogenic_claims == []  # input untouched


def test_reducer_resolves_conflicts():
    state = _state()
    state.conflicts = [Conflict(id="cf1", conflict_type="x", description="d", severity="high")]
    delta = JuryDelta(conflicts_to_resolve=["cf1"])
    new, result = reduce_state(state, delta, CrossExamResult(), [], [])
    assert result.conflicts_resolved == ["cf1"]
    assert new.conflicts[0].resolved is True


def test_convergence_requires_stable_state_and_no_high_conflicts():
    a = _state()
    b = a.model_copy(deep=True)
    assert has_converged(a, b)
    b.confidence_score = 0.5
    assert not has_converged(a, b)
    b = a.model_copy(deep=True)
    b.conflicts = [Conflict(id="cf", conflict_type="x", description="d", severity="high")]
    assert not has_converged(a, b)
    # Resolving a conflict is cleanup, so the round that closes it can converge; a new one blocks.
    c = b.model_copy(deep=True)
    c.conflicts[0].resolved = True
    assert has_converged(b, c)
    d = c.model_copy(deep=True)
    d.conflicts.append(Conflict(id="cf2", conflict_type="y", description="d", severity="medium"))
    assert not has_converged(c, d)
