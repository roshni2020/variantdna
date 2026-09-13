"""Hackathon-friendly convergence check.

Converged when, between two consecutive states:
- criterion proposals are unchanged,
- the confidence score moved less than a threshold,
- the set of live claims (and their statuses) is unchanged,
- no new medium/high conflict was added,
- and no unresolved high-severity conflict remains.

Never converge just because a model says "final".
"""

from __future__ import annotations

from variantcourt.domain import EvidenceState

CONFIDENCE_THRESHOLD = 0.03


def _claim_signature(state: EvidenceState) -> set[tuple[str, str]]:
    # Only criterion-bearing claims can move the verdict; context remarks are noise for convergence.
    return {
        (c.id, state.claim_status.get(c.id, "unchanged"))
        for c in state.pathogenic_claims + state.benign_claims
        if c.proposed_criterion
    }


def has_converged(old: EvidenceState, new: EvidenceState, threshold: float = CONFIDENCE_THRESHOLD) -> bool:
    same_criteria = old.criterion_states == new.criterion_states
    confidence_delta = abs(old.confidence_score - new.confidence_score)
    same_claims = _claim_signature(old) == _claim_signature(new)
    # New medium/high conflicts mean movement; old ones closing is cleanup and may coincide with stability.
    open_before = {c.id for c in old.conflicts if not c.resolved and c.severity != "low"}
    open_now = {c.id for c in new.conflicts if not c.resolved and c.severity != "low"}
    same_conflicts = open_now <= open_before
    unresolved_high = any(c.severity == "high" and not c.resolved for c in new.conflicts)
    return same_criteria and confidence_delta < threshold and same_claims and same_conflicts and not unresolved_high
