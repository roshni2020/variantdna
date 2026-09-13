import pytest
from pydantic import ValidationError

from variantcourt.domain import AgentClaim, EvidenceItem, EvidenceState, NormalizedVariant, compute_state_hash
from variantcourt.evidence import normalize_variant, variant_key


def test_normalize_transcript_hgvs():
    v = normalize_variant("NM_007294.4:c.68_69delAG")
    assert v.transcript == "NM_007294.4"
    assert v.hgvs == "c.68_69delAG"
    assert variant_key(v) == "NM_007294.4:c.68_69delAG"


def test_normalize_gene_and_rsid():
    assert normalize_variant("BRCA1 c.4837A>G").gene == "BRCA1"
    assert normalize_variant("rs1799966").rsid == "rs1799966"
    assert normalize_variant("garbage").hgvs is None


def test_confidence_bounds_validated():
    with pytest.raises(ValidationError):
        EvidenceItem(id="x", source="s", evidence_type="t", summary="s", direction="benign", confidence=1.5)
    with pytest.raises(ValidationError):
        AgentClaim(id="c", agent="a", claim="x", evidence_ids=[], confidence=-0.1)


def test_direction_literal_enforced():
    with pytest.raises(ValidationError):
        EvidenceItem(id="x", source="s", evidence_type="t", summary="s", direction="maybe", confidence=0.5)


def test_state_hash_ignores_round_and_hash_fields():
    state = EvidenceState(variant=NormalizedVariant(input="x"))
    h1 = compute_state_hash(state)
    state.round = 5
    state.state_hash = "whatever"
    assert compute_state_hash(state) == h1
    state.confidence_score = 0.5
    assert compute_state_hash(state) != h1
