"""Checks for the review findings: allele matching, transcript honesty, conflict reopening."""

from variantcourt.domain import Conflict, CrossExamResult, EvidenceState, JuryDelta, NormalizedVariant
from variantcourt.evidence import sources
from variantcourt.loopcore import reduce_state


def test_population_fallback_uses_the_variant_allele():
    rec = {"allele_string": "A/G", "colocated_variants": [{"id": "rs1", "frequencies": {"T": {"gnomade": 0.4}, "G": {"gnomade": 0.001}}}]}
    item = sources.vep_population_item(rec, "NM_1.1")
    assert item is not None and item.metadata["allele_frequency"] == 0.001
    rec["colocated_variants"][0]["frequencies"] = {"T": {"gnomade": 0.4}}
    assert sources.vep_population_item(rec, "NM_1.1") is None


def test_requested_transcript_is_not_silently_replaced():
    rec = {"transcript_consequences": [{"transcript_id": "NM_999.1", "gene_symbol": "BRCA1", "consequence_terms": ["missense_variant"], "canonical": 1}], "colocated_variants": []}
    items, enriched = sources.vep_items(rec, NormalizedVariant(input="x", transcript="NM_007294.4", hgvs="c.1A>G"))
    assert enriched.transcript == "NM_007294.4"
    cons = next(i for i in items if i.id == "ev_vep_consequence")
    assert cons.transcript == "NM_999.1"
    assert cons.metadata["requested_transcript_annotated"] is False


def test_reducer_reopens_resolved_conflict_when_raised_again():
    state = EvidenceState(variant=NormalizedVariant(input="v"), conflicts=[Conflict(id="cf", conflict_type="x", description="d", severity="high", resolved=True)])
    raised = Conflict(id="cf", conflict_type="x", description="d", severity="high")
    new, result = reduce_state(state, JuryDelta(conflicts_to_add=[raised]), CrossExamResult(contradictions=[raised]), [], [])
    assert result.conflicts_added == ["cf"]
    assert new.unresolved_conflicts("high")
