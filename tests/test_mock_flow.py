"""End-to-end tests over the mocked courtroom loop."""

import pytest

from variantcourt.loopcore import CourtroomConfig, CourtroomRunner, InMemoryTracer


async def _run(variant: str, rounds: int = 3):
    tracer = InMemoryTracer()
    runner = CourtroomRunner(tracer=tracer, config=CourtroomConfig(max_rounds=rounds))
    return await runner.run(variant), tracer


@pytest.mark.asyncio
async def test_pathogenic_demo_case_converges_and_classifies():
    result, tracer = await _run("NM_007294.4:c.68_69delAG")
    v = result.verdict
    assert v.classification == "Pathogenic"
    assert result.state.converged is True
    assert v.rounds_used == 2
    last_changes = result.rounds[-1].round_result.changes
    assert all(ch.startswith("Conflict resolved") for ch in last_changes), "final round may only clean up conflicts"
    assert v.requires_human_review is False
    assert not result.state.unresolved_conflicts("high")

    r1 = result.rounds[0].cross_exam
    types = {c.conflict_type for c in r1.contradictions}
    assert "transcript_mismatch" in types, "TypeSafe must catch the alternate-transcript trap in round 1"
    assert "unsupported_claim" in types, "TypeSafe must reject the over-read population observation"
    assert r1.rejected_claim_ids

    # Something changed between rounds and the loop actually improved.
    assert result.rounds[0].round_result.conflicts_added
    assert any(s.round_result.conflicts_resolved for s in result.rounds[1:])
    last = result.rounds[-1].cross_exam
    assert not last.rejected_claim_ids
    assert tracer.rounds[1]["number_of_rejected_claims"] > tracer.rounds[len(result.rounds)]["number_of_rejected_claims"]

    # Hashes chain and change.
    hashes = [s.round_result.new_state_hash for s in result.rounds]
    assert result.rounds[0].round_result.previous_state_hash != hashes[0]
    for a, b in zip(result.rounds, result.rounds[1:]):
        assert a.round_result.new_state_hash == b.round_result.previous_state_hash

    # Evidence immutable across the run.
    assert result.state.evidence_items == result.rounds[0].state_after.evidence_items


@pytest.mark.asyncio
async def test_benign_demo_case():
    result, _ = await _run("NM_007294.4:c.4837A>G")
    assert result.verdict.classification == "Benign"
    codes = {c.code: c.status for c in result.verdict.criteria}
    assert codes["BA1"] == "STAND_ALONE"
    assert codes["BP4"] == "SUPPORTING"
    # The pathogenic counsel's missense speculation is weakened, not accepted.
    assert result.rounds[0].cross_exam.weakened_claim_ids
    assert all(result.state.claim_status[c.id] == "weaken" for c in result.state.pathogenic_claims)


@pytest.mark.asyncio
async def test_unknown_variant_abstains():
    result, _ = await _run("NM_000000.1:c.1A>G")
    assert result.verdict.classification == "Insufficient Evidence"
    assert result.verdict.requires_human_review is True
    assert result.state.sources_loaded == ["Ensembl VEP"]


@pytest.mark.asyncio
async def test_all_claims_cite_existing_evidence():
    result, tracer = await _run("NM_007294.4:c.68_69delAG")
    known = result.state.evidence_ids()
    for snap in result.rounds:
        for c in snap.pathogenic_claims + snap.benign_claims:
            assert c.evidence_ids and set(c.evidence_ids) <= known
    assert all(m["citation_validity"] == 1.0 for m in tracer.rounds.values())


@pytest.mark.asyncio
async def test_max_rounds_one_reports_needs_review_when_high_conflict_open():
    result, _ = await _run("NM_007294.4:c.68_69delAG", rounds=1)
    assert result.verdict.rounds_used == 1
    assert result.verdict.classification == "NEEDS_REVIEW"
    assert result.verdict.requires_human_review is True
