"""Agent interfaces. LLM-backed implementations must satisfy the same protocols."""

from __future__ import annotations

import hashlib
from typing import Protocol

from variantcourt.domain import AgentClaim, CrossExamResult, EvidenceState, JuryDelta


class CounselAgent(Protocol):
    name: str

    async def run(self, state: EvidenceState, opponent: list[AgentClaim] | None = None) -> list[AgentClaim]: ...


class JuryAgent(Protocol):
    name: str

    async def run(
        self,
        state: EvidenceState,
        pathogenic_claims: list[AgentClaim],
        benign_claims: list[AgentClaim],
        cross_exam: CrossExamResult,
    ) -> JuryDelta: ...


def claim_id(agent: str, criterion: str | None, evidence_ids: list[str]) -> str:
    """Deterministic claim id: the same argument gets the same id in every round.

    That lets EvidenceState.claim_status track jury decisions without any chat history.
    """
    # ponytail: identity = side + evidence set, not the criterion label. Once a side loses an
    # argument on some evidence, relabeling it (BS1 -> BA1 -> PM2) yields the same id and is blocked.
    prefix = "path" if "pathogenic" in agent else "ben"
    digest = hashlib.sha1(",".join(sorted(evidence_ids)).encode()).hexdigest()[:6]
    return f"claim_{prefix}_{digest}"


def was_rejected(state: EvidenceState, cid: str) -> bool:
    return state.claim_status.get(cid) == "reject"


def was_weakened(state: EvidenceState, cid: str) -> bool:
    return state.claim_status.get(cid) == "weaken"


def flagged_evidence_ids(state: EvidenceState) -> set[str]:
    """Evidence referenced by unresolved or resolved transcript-mismatch conflicts.

    Agents read this from state so they stop citing evidence TypeSafe already threw out.
    """
    flagged: set[str] = set()
    claims = {c.id: c for c in state.pathogenic_claims + state.benign_claims}
    for conflict in state.conflicts:
        if conflict.conflict_type != "transcript_mismatch":
            continue
        for cid in conflict.affected_claim_ids:
            if cid in claims:
                flagged.update(claims[cid].evidence_ids)
    # Also anything whose transcript plainly differs; the mock agents are allowed to
    # notice this only after a conflict was recorded, to keep round 1 interesting.
    return flagged
