"""Simplified ACMG-style research rules. Not for clinical use.

Each criterion is a pure function over structured evidence in EvidenceState.
Evidence annotated on a transcript other than the case transcript is ignored.
"""

from __future__ import annotations

from collections.abc import Callable

from variantcourt.domain import CriterionResult, EvidenceItem, EvidenceState

NOT_EVALUATED = "NOT_EVALUATED"
NOT_MET = "NOT_MET"
SUPPORTING = "SUPPORTING"
MODERATE = "MODERATE"
STRONG = "STRONG"
VERY_STRONG = "VERY_STRONG"
STAND_ALONE = "STAND_ALONE"

LOF_CONSEQUENCES = {
    "frameshift_variant",
    "stop_gained",
    "splice_acceptor_variant",
    "splice_donor_variant",
    "start_lost",
}

PM2_MAX_AF = 1e-4
BS1_MIN_AF = 0.01
BA1_MIN_AF = 0.05


def usable_evidence(state: EvidenceState) -> list[EvidenceItem]:
    tx = state.variant.transcript
    return [e for e in state.evidence_items if not tx or not e.transcript or e.transcript == tx]


def _population(state: EvidenceState) -> list[EvidenceItem]:
    return [
        e for e in usable_evidence(state)
        if e.evidence_type == "population_frequency" and "allele_frequency" in e.metadata
    ]


def evaluate_pvs1(state: EvidenceState) -> CriterionResult:
    hits = [
        e for e in usable_evidence(state)
        if e.evidence_type == "consequence" and e.metadata.get("consequence") in LOF_CONSEQUENCES
    ]
    if not hits:
        return CriterionResult(code="PVS1", status=NOT_MET, rationale="No loss-of-function consequence annotated.")
    if any(e.metadata.get("lof_mechanism") for e in hits):
        if any(_in_last_exon(e) for e in hits):
            # ClinGen PVS1 guidance: a truncation in the last exon is expected to escape
            # nonsense-mediated decay, so the protein may survive. ponytail: always Moderate;
            # the full decision tree also weighs the share of protein removed and critical domains.
            return CriterionResult(
                code="PVS1", status=MODERATE, evidence_ids=[e.id for e in hits],
                rationale=f"{hits[0].metadata['consequence']} in the last exon ({hits[0].metadata.get('exon')}); "
                "likely escapes nonsense-mediated decay, so PVS1 is downgraded to Moderate.",
            )
        return CriterionResult(
            code="PVS1",
            status=VERY_STRONG,
            evidence_ids=[e.id for e in hits],
            rationale=f"{hits[0].metadata['consequence']} in a gene with an established loss-of-function mechanism.",
        )
    return CriterionResult(
        code="PVS1",
        status=NOT_MET,
        evidence_ids=[e.id for e in hits],
        rationale="Loss-of-function consequence present but disease mechanism not established.",
    )


def _in_last_exon(e: EvidenceItem) -> bool:
    n, _, total = str(e.metadata.get("exon") or "").partition("/")
    return bool(total) and n == total


def evaluate_ps1(state: EvidenceState) -> CriterionResult:
    hits = [e for e in usable_evidence(state) if e.metadata.get("same_aa_change_pathogenic")]
    if hits:
        return CriterionResult(
            code="PS1", status=STRONG, evidence_ids=[e.id for e in hits],
            rationale="Same amino-acid change as an established pathogenic variant.",
        )
    return CriterionResult(code="PS1", status=NOT_MET, rationale="No established pathogenic variant with the same amino-acid change.")


def evaluate_ps3(state: EvidenceState) -> CriterionResult:
    hits = [
        e for e in usable_evidence(state)
        if e.evidence_type == "functional" and e.direction == "pathogenic" and e.confidence >= 0.6
    ]
    if hits:
        return CriterionResult(
            code="PS3", status=STRONG, evidence_ids=[e.id for e in hits],
            rationale="Well-established functional study shows a damaging effect.",
        )
    return CriterionResult(code="PS3", status=NOT_MET, rationale="No damaging functional evidence of sufficient quality.")


def evaluate_pm2(state: EvidenceState) -> CriterionResult:
    pop = _population(state)
    if not pop:
        return CriterionResult(code="PM2", status=NOT_EVALUATED, rationale="No population frequency data available.")
    af = min(e.metadata["allele_frequency"] for e in pop)
    if af < PM2_MAX_AF:
        return CriterionResult(
            code="PM2", status=MODERATE, evidence_ids=[e.id for e in pop],
            rationale=f"Allele frequency {af:.2g} is below the {PM2_MAX_AF:g} rarity threshold.",
        )
    return CriterionResult(code="PM2", status=NOT_MET, evidence_ids=[e.id for e in pop], rationale=f"Allele frequency {af:.2g} is not rare.")


def evaluate_ba1(state: EvidenceState) -> CriterionResult:
    pop = _population(state)
    if not pop:
        return CriterionResult(code="BA1", status=NOT_EVALUATED, rationale="No population frequency data available.")
    af = max(e.metadata["allele_frequency"] for e in pop)
    if af > BA1_MIN_AF:
        return CriterionResult(
            code="BA1", status=STAND_ALONE, evidence_ids=[e.id for e in pop],
            rationale=f"Allele frequency {af:.2g} exceeds {BA1_MIN_AF:g}; stand-alone benign.",
        )
    return CriterionResult(code="BA1", status=NOT_MET, evidence_ids=[e.id for e in pop], rationale=f"Allele frequency {af:.2g} does not exceed {BA1_MIN_AF:g}.")


def evaluate_bs1(state: EvidenceState) -> CriterionResult:
    pop = _population(state)
    if not pop:
        return CriterionResult(code="BS1", status=NOT_EVALUATED, rationale="No population frequency data available.")
    af = max(e.metadata["allele_frequency"] for e in pop)
    if BS1_MIN_AF < af <= BA1_MIN_AF:
        return CriterionResult(
            code="BS1", status=STRONG, evidence_ids=[e.id for e in pop],
            rationale=f"Allele frequency {af:.2g} is greater than expected for the disorder.",
        )
    return CriterionResult(code="BS1", status=NOT_MET, evidence_ids=[e.id for e in pop], rationale=f"Allele frequency {af:.2g} is outside the BS1 window.")


def evaluate_bs3(state: EvidenceState) -> CriterionResult:
    hits = [
        e for e in usable_evidence(state)
        if e.evidence_type == "functional" and e.direction == "benign" and e.confidence >= 0.6
    ]
    if hits:
        return CriterionResult(
            code="BS3", status=STRONG, evidence_ids=[e.id for e in hits],
            rationale="Well-established functional study shows no damaging effect.",
        )
    return CriterionResult(code="BS3", status=NOT_MET, rationale="No benign functional evidence of sufficient quality.")


def evaluate_bp4(state: EvidenceState) -> CriterionResult:
    hits = [e for e in usable_evidence(state) if e.evidence_type == "in_silico" and e.direction == "benign"]
    if hits:
        return CriterionResult(
            code="BP4", status=SUPPORTING, evidence_ids=[e.id for e in hits],
            rationale="Computational evidence suggests no impact.",
        )
    return CriterionResult(code="BP4", status=NOT_MET, rationale="No benign computational evidence.")


def evaluate_bp7(state: EvidenceState) -> CriterionResult:
    """Synonymous change with no predicted splicing impact. ponytail: splicing impact is read from
    VEP's splice-region terms only; SpliceAI scores would be the stronger check."""
    hits = [
        e for e in usable_evidence(state)
        if e.evidence_type == "consequence" and e.metadata.get("consequence") == "synonymous_variant"
        and not any("splice" in t for t in e.metadata.get("consequence_terms") or [])
    ]
    if hits:
        return CriterionResult(
            code="BP7", status=SUPPORTING, evidence_ids=[e.id for e in hits],
            rationale="Synonymous change (protein unchanged) outside annotated splice regions.",
        )
    return CriterionResult(code="BP7", status=NOT_MET, rationale="Not a synonymous change, or it touches a splice region.")


def _prior(state: EvidenceState, direction: str) -> list[EvidenceItem]:
    return [
        e for e in usable_evidence(state)
        if e.evidence_type == "prior_classification" and e.direction == direction and (e.metadata.get("stars") or 0) >= 2
    ]


def _reputable(code: str, direction: str, state: EvidenceState) -> CriterionResult:
    """PP5 / BP6 (reputable source). Research shortcut: a 3+ star expert-panel or practice-
    guideline ClinVar classification counts as STRONG, a 2-star multi-submitter consensus as
    SUPPORTING. Not for clinical use; these codes were retired from clinical ACMG practice."""
    hits = _prior(state, direction)
    if not hits:
        return CriterionResult(code=code, status=NOT_MET, rationale=f"No reviewed {direction} classification from a reputable source.")
    best = max(hits, key=lambda e: e.metadata.get("stars") or 0)
    stars = best.metadata.get("stars") or 0
    status = STRONG if stars >= 3 else SUPPORTING
    return CriterionResult(
        code=code,
        status=status,
        evidence_ids=[e.id for e in hits],
        rationale=f"{best.source} {best.metadata.get('review_status', 'reviewed')} ({stars} stars) reports {best.metadata.get('classification', direction)}. Research shortcut, not clinical practice.",
    )


def evaluate_pp5(state: EvidenceState) -> CriterionResult:
    return _reputable("PP5", "pathogenic", state)


def evaluate_bp6(state: EvidenceState) -> CriterionResult:
    return _reputable("BP6", "benign", state)


CRITERIA: dict[str, Callable[[EvidenceState], CriterionResult]] = {
    "PVS1": evaluate_pvs1,
    "PS1": evaluate_ps1,
    "PS3": evaluate_ps3,
    "PM2": evaluate_pm2,
    "BA1": evaluate_ba1,
    "BS1": evaluate_bs1,
    "BS3": evaluate_bs3,
    "BP4": evaluate_bp4,
    "BP7": evaluate_bp7,
    "PP5": evaluate_pp5,
    "BP6": evaluate_bp6,
}


def evaluate_all(state: EvidenceState) -> list[CriterionResult]:
    return [fn(state) for fn in CRITERIA.values()]
