"""Deterministic demo fixtures for DEMO MODE.

Each fixture is a full evidence bundle for one variant. Fixtures deliberately include
"traps" (transcript mismatch, stale submissions, neutral observations that a counsel might
over-read) so that the TypeSafe cross-examiner has something meaningful to find.
"""

from __future__ import annotations

from variantcourt.domain import DiseaseContext, EvidenceItem, NormalizedVariant


def _ev(**kw) -> EvidenceItem:
    return EvidenceItem(**kw)


HBOC = DiseaseContext(
    disease_name="Hereditary breast and ovarian cancer syndrome", mondo_id="MONDO:0016419"
)

BRCA1_185DELAG = {
    "variant": NormalizedVariant(
        input="NM_007294.4:c.68_69delAG",
        gene="BRCA1",
        transcript="NM_007294.4",
        hgvs="c.68_69delAG",
        rsid="rs386833395",
        assembly="GRCh38",
    ),
    "disease_context": HBOC,
    "sources": ["ClinVar", "Ensembl VEP", "gnomAD", "Europe PMC"],
    "evidence": [
        _ev(
            id="ev_clinvar_001",
            source="ClinVar",
            evidence_type="prior_classification",
            summary="Expert panel (ENIGMA) classifies this variant as Pathogenic for hereditary breast and ovarian cancer.",
            direction="pathogenic",
            confidence=0.95,
            source_identifier="VCV000017677",
            source_url="https://www.ncbi.nlm.nih.gov/clinvar/variation/17677/",
            transcript="NM_007294.4",
            metadata={"review_status": "reviewed by expert panel", "stars": 3, "submission_year": 2019},
        ),
        _ev(
            id="ev_vep_001",
            source="Ensembl VEP",
            evidence_type="consequence",
            summary="Frameshift variant (p.Glu23ValfsTer17) in BRCA1 canonical transcript; predicted loss of function.",
            direction="pathogenic",
            confidence=0.85,
            transcript="NM_007294.4",
            metadata={
                "consequence": "frameshift_variant",
                "protein_change": "p.Glu23ValfsTer17",
                "lof_mechanism": True,
                "nmd_predicted": True,
            },
        ),
        _ev(
            id="ev_gnomad_001",
            source="gnomAD",
            evidence_type="population_frequency",
            summary="Allele frequency 7.9e-06 in gnomAD v4 (2 alleles / 251,000).",
            direction="pathogenic",
            confidence=0.80,
            transcript="NM_007294.4",
            metadata={"allele_frequency": 7.9e-06, "allele_count": 2, "allele_number": 251000, "popmax_af": 3.1e-05},
        ),
        _ev(
            id="ev_vep_002",
            source="Ensembl VEP",
            evidence_type="consequence",
            summary="Frameshift annotation on alternate transcript NM_007300.4 (c.68_69delAG).",
            direction="pathogenic",
            confidence=0.60,
            transcript="NM_007300.4",
            metadata={"consequence": "frameshift_variant", "lof_mechanism": True, "canonical": False},
        ),
        _ev(
            id="ev_clinvar_002",
            source="ClinVar",
            evidence_type="prior_classification",
            summary="Single 2005 submitter entry listed as Uncertain significance with no assertion criteria provided.",
            direction="neutral",
            confidence=0.30,
            source_identifier="SCV000000451",
            transcript="NM_007294.4",
            metadata={"review_status": "no assertion criteria provided", "stars": 0, "submission_year": 2005, "stale": True},
        ),
        _ev(
            id="ev_pubmed_001",
            source="Europe PMC",
            evidence_type="functional",
            summary="Functional assay: truncated protein lacks BRCT domains and fails homology-directed repair complementation.",
            direction="pathogenic",
            confidence=0.75,
            source_identifier="PMID:9497265",
            metadata={"assay": "HDR complementation", "result": "loss of function"},
        ),
        _ev(
            id="ev_gnomad_002",
            source="gnomAD",
            evidence_type="population_observation",
            summary="Two heterozygous carriers observed in gnomAD; carrier phenotype not available.",
            direction="neutral",
            confidence=0.40,
            transcript="NM_007294.4",
            metadata={"observed_in_controls": True, "allele_count": 2, "allele_frequency": 7.9e-06},
        ),
    ],
}

BRCA1_S1613G = {
    "variant": NormalizedVariant(
        input="NM_007294.4:c.4837A>G",
        gene="BRCA1",
        transcript="NM_007294.4",
        hgvs="c.4837A>G",
        rsid="rs1799966",
        assembly="GRCh38",
    ),
    "disease_context": HBOC,
    "sources": ["ClinVar", "Ensembl VEP", "gnomAD", "Europe PMC"],
    "evidence": [
        _ev(
            id="ev_clinvar_101",
            source="ClinVar",
            evidence_type="prior_classification",
            summary="Expert panel classifies p.Ser1613Gly as Benign.",
            direction="benign",
            confidence=0.95,
            source_identifier="VCV000041970",
            transcript="NM_007294.4",
            metadata={"review_status": "reviewed by expert panel", "stars": 3, "submission_year": 2020},
        ),
        _ev(
            id="ev_vep_101",
            source="Ensembl VEP",
            evidence_type="consequence",
            summary="Missense variant p.Ser1613Gly in BRCA1 BRCT domain.",
            direction="neutral",
            confidence=0.50,
            transcript="NM_007294.4",
            metadata={"consequence": "missense_variant", "protein_change": "p.Ser1613Gly"},
        ),
        _ev(
            id="ev_gnomad_101",
            source="gnomAD",
            evidence_type="population_frequency",
            summary="Allele frequency 0.31 in gnomAD v4; common in all major populations.",
            direction="benign",
            confidence=0.95,
            transcript="NM_007294.4",
            metadata={"allele_frequency": 0.31, "allele_count": 249000, "allele_number": 803000, "homozygotes": 39000},
        ),
        _ev(
            id="ev_insilico_101",
            source="Ensembl VEP",
            evidence_type="in_silico",
            summary="REVEL 0.08, SIFT tolerated, PolyPhen benign.",
            direction="benign",
            confidence=0.70,
            transcript="NM_007294.4",
            metadata={"revel": 0.08, "sift": "tolerated", "polyphen": "benign"},
        ),
        _ev(
            id="ev_pubmed_101",
            source="Europe PMC",
            evidence_type="functional",
            summary="Transcription activation and HDR assays show wild-type activity for S1613G.",
            direction="benign",
            confidence=0.70,
            source_identifier="PMID:20516115",
            metadata={"assay": "transcription activation", "result": "wild-type"},
        ),
    ],
}

FIXTURES: dict[str, dict] = {
    "NM_007294.4:c.68_69delAG": BRCA1_185DELAG,
    "NM_007294.4:c.68_69del": BRCA1_185DELAG,
    "BRCA1:c.68_69delAG": BRCA1_185DELAG,
    "rs386833395": BRCA1_185DELAG,
    "NM_007294.4:c.4837A>G": BRCA1_S1613G,
    "BRCA1:c.4837A>G": BRCA1_S1613G,
    "rs1799966": BRCA1_S1613G,
}


def sparse_fixture(variant: NormalizedVariant) -> dict:
    """Minimal bundle for unknown variants so the courtroom can still run and abstain."""
    return {
        "variant": variant,
        "disease_context": None,
        "sources": ["Ensembl VEP"],
        "evidence": [
            _ev(
                id="ev_vep_901",
                source="Ensembl VEP",
                evidence_type="consequence",
                summary=f"Missense variant annotation for {variant.input} (mock). No population or clinical data available.",
                direction="neutral",
                confidence=0.50,
                transcript=variant.transcript,
                metadata={"consequence": "missense_variant"},
            )
        ],
    }
