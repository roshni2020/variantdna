"""Deterministic combination of criteria into a classification.

Simplified ACMG-style research rules (after Richards et al. 2015). Not for clinical use.
"""

from __future__ import annotations

from variantcourt.domain import CriterionResult, EvidenceState, Verdict

from .criteria import (
    MODERATE,
    NOT_EVALUATED,
    NOT_MET,
    STAND_ALONE,
    STRONG,
    SUPPORTING,
    VERY_STRONG,
    evaluate_all,
    usable_evidence,
)

DISCLAIMER = "Simplified ACMG-style research rules. Not for clinical use."

PATHOGENIC = "Pathogenic"
LIKELY_PATHOGENIC = "Likely Pathogenic"
VUS = "VUS"
LIKELY_BENIGN = "Likely Benign"
BENIGN = "Benign"
INSUFFICIENT = "Insufficient Evidence"
NEEDS_REVIEW = "NEEDS_REVIEW"


def combine(criteria: list[CriterionResult], evidence_count: int) -> str:
    met = [c for c in criteria if c.status not in (NOT_MET, NOT_EVALUATED)]
    path = [c for c in met if c.code.startswith("P")]
    ben = [c for c in met if c.code.startswith("B")]

    vs = sum(1 for c in path if c.status == VERY_STRONG)
    s = sum(1 for c in path if c.status == STRONG)
    m = sum(1 for c in path if c.status == MODERATE)
    p = sum(1 for c in path if c.status == SUPPORTING)
    ba = any(c.status == STAND_ALONE for c in ben)
    bs = sum(1 for c in ben if c.status == STRONG)
    bp = sum(1 for c in ben if c.status == SUPPORTING)

    pathogenic = (
        (vs >= 1 and (s >= 1 or m >= 2 or (m >= 1 and p >= 1) or p >= 2))
        or s >= 2
        or (s == 1 and (m >= 3 or (m == 2 and p >= 2) or (m == 1 and p >= 4)))
    )
    likely_pathogenic = (
        (vs >= 1 and m == 1)
        or (s == 1 and 1 <= m <= 2)
        or (s == 1 and p >= 2)
        or m >= 3
        or (m == 2 and p >= 2)
        or (m == 1 and p >= 4)
    )
    benign = ba or bs >= 2
    likely_benign = (bs == 1 and bp >= 1) or bp >= 2

    if ba:
        return BENIGN
    if path and ben:
        # Conflicting pathogenic and benign criteria: do not pick a side.
        return VUS
    if pathogenic:
        return PATHOGENIC
    if likely_pathogenic:
        return LIKELY_PATHOGENIC
    if benign:
        return BENIGN
    if likely_benign:
        return LIKELY_BENIGN
    if not met and (evidence_count < 2 or all(c.status == NOT_EVALUATED for c in criteria if c.code in ("PM2", "BA1", "BS1"))):
        return INSUFFICIENT
    return VUS


# Bayesian point system (Tavtigian et al. 2018/2020). PM2 counts as supporting per ClinGen SVI.
_POINTS = {SUPPORTING: 1, MODERATE: 2, STRONG: 4, VERY_STRONG: 8}


def combine_points(criteria: list[CriterionResult], evidence_count: int) -> str:
    """Sum pathogenic minus benign points; conflicting evidence nets out instead of forcing VUS."""
    met = [c for c in criteria if c.status not in (NOT_MET, NOT_EVALUATED)]
    if any(c.status == STAND_ALONE for c in met):
        return BENIGN
    score = 0
    for c in met:
        pts = 1 if c.code == "PM2" else _POINTS.get(c.status, 0)
        score += pts if c.code.startswith("P") else -pts
    if score >= 10:
        return PATHOGENIC
    if score >= 6:
        return LIKELY_PATHOGENIC
    if score <= -7:
        return BENIGN
    if score <= -1:
        return LIKELY_BENIGN
    if not met and (evidence_count < 2 or all(c.status == NOT_EVALUATED for c in criteria if c.code in ("PM2", "BA1", "BS1"))):
        return INSUFFICIENT
    return VUS


def evaluate_verdict(state: EvidenceState, max_rounds: int, scoring: str = "rules") -> Verdict:
    """scoring: "rules" (Richards 2015 combining rules, default) or "points" (Tavtigian)."""
    criteria = evaluate_all(state)
    unresolved_high = state.unresolved_conflicts("high")
    classification = (combine_points if scoring == "points" else combine)(criteria, evidence_count=len(usable_evidence(state)))

    if unresolved_high and state.round >= max_rounds and not state.converged:
        classification = NEEDS_REVIEW

    requires_review = bool(unresolved_high) or classification in (VUS, INSUFFICIENT, NEEDS_REVIEW)
    return Verdict(
        classification=classification,
        criteria=criteria,
        unresolved_conflicts=state.unresolved_conflicts(),
        rounds_used=state.round,
        requires_human_review=requires_review,
        converged=state.converged,
        disclaimer=DISCLAIMER,
    )
