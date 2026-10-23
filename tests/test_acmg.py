from variantcourt.acmg import combine, evaluate_all
from variantcourt.acmg.combine import combine_points
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


def test_points_scoring_nets_out_conflicts():
    # Rare but benign: PM2 (1) vs BP4 + BP6 (-2). Rules mode abstains; points mode leans benign.
    rare_benign = [_cr("PM2", "MODERATE"), _cr("BP4", "SUPPORTING"), _cr("BP6", "SUPPORTING")]
    assert combine(rare_benign, 5) == "VUS"
    assert combine_points(rare_benign, 5) == "Likely Benign"
    # Frameshift in an LoF gene, absent from gnomAD, ClinVar pathogenic: 8 + 1 + 1.
    assert combine_points([_cr("PVS1", "VERY_STRONG"), _cr("PM2", "MODERATE"), _cr("PP5", "SUPPORTING")], 5) == "Pathogenic"
    assert combine_points([_cr("PVS1", "VERY_STRONG")], 5) == "Likely Pathogenic"
    assert combine_points([_cr("BS1", "STRONG"), _cr("BS3", "STRONG")], 5) == "Benign"
    assert combine_points([_cr("BA1", "STAND_ALONE"), _cr("PVS1", "VERY_STRONG")], 5) == "Benign"
    assert combine_points([_cr("PM2", "NOT_EVALUATED")], 1) == "Insufficient Evidence"


def _vep(consequence, **meta):
    return EvidenceItem(
        id="ev_vep_consequence", source="Ensembl VEP", evidence_type="consequence", summary="", direction="neutral",
        confidence=0.8, transcript="NM_1.1", metadata={"consequence": consequence, **meta},
    )


def _crit(state, code):
    return next(c for c in evaluate_all(state) if c.code == code)


def test_bp7_synonymous_and_pvs1_last_exon():
    v = NormalizedVariant(input="NM_1.1:c.1A>G", transcript="NM_1.1")
    syn = EvidenceState(variant=v, evidence_items=[_vep("synonymous_variant", consequence_terms=["synonymous_variant"])])
    assert _crit(syn, "BP7").status == "SUPPORTING"
    near_splice = EvidenceState(variant=v, evidence_items=[_vep("synonymous_variant", consequence_terms=["synonymous_variant", "splice_region_variant"])])
    assert _crit(near_splice, "BP7").status == "NOT_MET"
    # BRCA2 p.Ser3366fs sits in exon 27 of 27: escapes NMD, so PVS1 only Moderate.
    last = EvidenceState(variant=v, evidence_items=[_vep("stop_gained", lof_mechanism=True, exon="27/27")])
    assert _crit(last, "PVS1").status == "MODERATE"
    early = EvidenceState(variant=v, evidence_items=[_vep("stop_gained", lof_mechanism=True, exon="11/27")])
    assert _crit(early, "PVS1").status == "VERY_STRONG"
