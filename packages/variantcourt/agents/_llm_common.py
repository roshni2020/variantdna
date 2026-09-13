"""Shared helpers for LLM-backed agents."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from variantcourt.domain import AgentClaim, EvidenceState

from .base import claim_id

log = logging.getLogger(__name__)


class ClaimList(BaseModel):
    claims: list[AgentClaim] = Field(default_factory=list)


def sanitize_claims(claims: list[AgentClaim], state: EvidenceState, agent_name: str) -> list[AgentClaim]:
    """Drop claims citing unknown evidence or previously rejected ids; normalize ids/agent."""
    known = state.evidence_ids()
    out: list[AgentClaim] = []
    seen: set[str] = set()
    for c in claims:
        if not c.evidence_ids or any(e not in known for e in c.evidence_ids):
            log.info("dropping %s: unknown evidence %s", c.id, c.evidence_ids)
            continue
        # Deterministic id from (criterion, evidence): the same argument gets the same id in
        # every round, so a rejected argument cannot come back under a new name.
        cid = claim_id(agent_name, c.proposed_criterion, c.evidence_ids)
        if state.claim_status.get(cid) == "reject":
            log.info("dropping %s: rejected in an earlier round", cid)
            continue
        if cid in seen:
            continue
        seen.add(cid)
        conf = min(c.confidence, 0.35) if state.claim_status.get(cid) == "weaken" else c.confidence
        out.append(c.model_copy(update={"id": cid, "agent": agent_name, "confidence": conf}))
    return out


def provider_source(provider) -> str:
    return getattr(provider, "last_used", None) or getattr(provider, "name", "llm")
