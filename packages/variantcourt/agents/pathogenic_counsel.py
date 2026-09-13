"""Pathogenic Counsel: builds the strongest evidence-backed disease-causing case.

MockPathogenicCounsel: deterministic rules over EvidenceState (DEMO MODE).
LLMPathogenicCounsel: model-backed, schema-validated, falls back to the mock on failure.

Deterministic rules over EvidenceState. Cites only existing evidence ids and never
issues a classification. An LLM-backed version will replace the candidate generation
but keep the same filtering against claim_status.
"""

from __future__ import annotations

import logging

from variantcourt.domain import AgentClaim, EvidenceState
from variantcourt.providers.base import ModelProvider

from . import prompts
from ._llm_common import ClaimList, provider_source, sanitize_claims

from .base import claim_id, flagged_evidence_ids, was_rejected, was_weakened

log = logging.getLogger(__name__)

LOF = {"frameshift_variant", "stop_gained", "splice_acceptor_variant", "splice_donor_variant", "start_lost"}


class MockPathogenicCounsel:
    name = "pathogenic_counsel"

    async def run(self, state: EvidenceState, opponent: list[AgentClaim] | None = None) -> list[AgentClaim]:
        flagged = flagged_evidence_ids(state)
        candidates: list[AgentClaim] = []

        def propose(claim: str, evidence_ids: list[str], criterion: str | None, confidence: float, assumptions=()):
            cid = claim_id(self.name, criterion, evidence_ids)
            if was_rejected(state, cid):
                return
            if was_weakened(state, cid):
                confidence = min(confidence, 0.35)
            candidates.append(
                AgentClaim(
                    id=cid,
                    agent=self.name,
                    claim=claim,
                    evidence_ids=evidence_ids,
                    proposed_criterion=criterion,
                    confidence=confidence,
                    assumptions=list(assumptions),
                )
            )

        for ev in state.evidence_items:
            if ev.id in flagged:
                continue
            md = ev.metadata
            if ev.evidence_type == "consequence" and md.get("consequence") in LOF:
                propose(
                    f"{md.get('consequence', 'LoF').replace('_', ' ').capitalize()} predicted to abolish protein function "
                    f"in {state.variant.gene or 'the gene'}, a gene where loss of function is a known disease mechanism.",
                    [ev.id],
                    "PVS1",
                    0.9 if md.get("canonical", True) else 0.8,
                    ["Loss of function is the established mechanism for this gene."],
                )
            elif ev.evidence_type == "consequence" and md.get("consequence") == "missense_variant":
                propose(
                    "Missense change in a functional domain may disrupt protein activity.",
                    [ev.id],
                    None,
                    0.45,
                    ["Domain-level impact has not been demonstrated."],
                )
            elif ev.evidence_type == "population_frequency" and ev.direction == "pathogenic":
                propose(
                    "The variant is absent or extremely rare in population databases, consistent with a "
                    "high-penetrance disease allele.",
                    [ev.id],
                    "PM2",
                    0.85,
                )
            elif ev.evidence_type == "functional" and ev.direction == "pathogenic":
                propose(
                    "Well-established functional assay shows a damaging effect on protein function.",
                    [ev.id],
                    "PS3",
                    0.75,
                )
            elif ev.evidence_type == "prior_classification" and ev.direction == "pathogenic":
                stars = ev.metadata.get("stars") or 0
                propose(
                    "Prior reviewed classification from a reputable source supports a disease-causing interpretation.",
                    [ev.id],
                    "PP5" if stars >= 2 else None,
                    min(0.9, ev.confidence),
                    ["Reputable-source criterion is a research shortcut; the panel's own evidence is not re-examined here."],
                )
        return candidates


class LLMPathogenicCounsel:
    name = "pathogenic_counsel"

    def __init__(self, provider: ModelProvider):
        self.provider = provider
        self.fallback = MockPathogenicCounsel()
        self.last_source = "llm"

    async def run(self, state: EvidenceState, opponent: list[AgentClaim] | None = None) -> list[AgentClaim]:
        try:
            result = await self.provider.generate(
                prompts.counsel_system("pathogenic"), prompts.counsel_user(state, opponent or []), ClaimList
            )
            self.last_source = provider_source(self.provider)
            claims = sanitize_claims(result.claims, state, self.name)
            valid = {c.id for c in opponent or []}
            return [c.model_copy(update={"rebuts": c.rebuts if c.rebuts in valid else None}) for c in claims]
        except Exception as e:  # noqa: BLE001
            log.warning("%s LLM failed (%s); using deterministic fallback", self.name, e)
            self.last_source = "fallback(mock)"
            return await self.fallback.run(state, opponent)
