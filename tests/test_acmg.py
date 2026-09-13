from variantcourt.acmg import combine, evaluate_all
from variantcourt.domain import CriterionResult, EvidenceItem, EvidenceState, NormalizedVariant


def _cr(code, status):
    return CriterionResult(code=code, status=status, rationale="")


def test_combine_pathogenic_and_benign_paths():
    assert combine([_cr("PVS1", "VERY_STRONG"), _cr("PM2", "MODERATE"), _cr("PS3", "STRONG")], 5) == "Pathogenic"
    assert combine([_cr("PVS1", "VERY_STRONG"), _cr("PM2", "MODERATE")], 5) == "Likely Pathogenic"
    assert combine([_cr("BA1", "STAND_ALONE"), _cr("PVS1", "VERY_STRONG")], 5) == "Benign"
    assert combine([_cr("BS1", "STRONG"), _cr("BP4", "SUPPORTING")], 5) == "Likely Benign"
    assert combine([_cr("PS3", "STRONG"), _cr("BS3", "STRONG"), _cr("PM2", "MODERATE")], 5) == "VUS"


def test_combine_abstains_on_insufficient_evidence():
    crit = [_cr("PM2", "NOT_EVALUATED"), _cr("BA1", "NOT_EVALUATED"), _cr("BS1", "NOT_EVALUATED"), _cr("PVS1", "NOT_MET")]
    assert combine(crit, evidence_count=1) == "Insufficient Evidence"
    crit = [_cr("PM2", "NOT_MET"), _cr("BA1", "NOT_MET"), _cr("BS1", "NOT_MET"), _cr("PVS1", "NOT_MET")]
    assert combine(crit, evidence_count=4) == "VUS"


def test_criteria_ignore_mismatched_transcript_evidence():
    state = EvidenceState(
        variant=NormalizedVariant(input="v", transcript="NM_1.1"),
        evidence_items=[
            EvidenceItem(
                id="ev_other_tx", source="VEP", evidence_type="consequence", summary="", direction="pathogenic",
                confidence=0.6, transcript="NM_2.1", metadata={"consequence": "frameshift_variant", "lof_mechanism": True},
            ),
            EvidenceItem(
                id="ev_pop", source="gnomAD", evidence_type="population_frequency", summary="", direction="pathogenic",
                confidence=0.8, transcript="NM_1.1", metadata={"allele_frequency": 1e-6},
            ),
        ],
    )
    by_code = {c.code: c for c in evaluate_all(state)}
    assert by_code["PVS1"].status == "NOT_MET"
    assert by_code["PM2"].status == "MODERATE"
    assert by_code["PM2"].evidence_ids == ["ev_pop"]
