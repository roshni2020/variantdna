"""Benign Counsel: builds the strongest evidence-backed benign interpretation.

MockBenignCounsel: deterministic rules over EvidenceState (DEMO MODE).
LLMBenignCounsel: model-backed, schema-validated, falls back to the mock on failure.

Looks for high population frequency, benign prior classifications, benign functional and
in-silico evidence, and weak or uncertain disease association. Absence of evidence is not
treated as benign evidence. Cites only existing evidence ids; never classifies.
"""

from __future__ import annotations

import logging

from variantcourt.domain import AgentClaim, EvidenceState
from variantcourt.providers.base import ModelProvider

from . import prompts
from ._llm_common import ClaimList, provider_source, sanitize_claims

from .base import claim_id, flagged_evidence_ids, was_rejected, was_weakened

log = logging.getLogger(__name__)


class MockBenignCounsel:
    name = "benign_counsel"

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
            af = md.get("allele_frequency")
            if ev.evidence_type == "population_frequency" and af is not None and af > 0.05:
                propose(
                    f"Allele frequency {af:.2g} is far too common for a high-penetrance dominant disease allele.",
                    [ev.id],
                    "BA1",
                    0.95,
                )
            elif ev.evidence_type == "population_frequency" and af is not None and 0.01 < af <= 0.05:
                propose(
                    f"Allele frequency {af:.2g} exceeds what is expected for the disorder.",
                    [ev.id],
                    "BS1",
                    0.8,
                )
            elif ev.evidence_type == "population_observation" and md.get("observed_in_controls"):
                # Deliberately over-read: carriers observed does not mean healthy controls.
                propose(
                    "The variant has been observed in general-population individuals, suggesting tolerance.",
                    [ev.id],
                    "BS1",
                    0.7,
                    ["Population carriers are assumed to be unaffected."],
                )
            elif ev.evidence_type == "prior_classification" and ev.direction == "benign":
                stars = ev.metadata.get("stars") or 0
                propose(
                    "Prior reviewed classification from a reputable source supports a benign interpretation.",
                    [ev.id],
                    "BP6" if stars >= 2 else None,
                    min(0.9, ev.confidence),
                    ["Reputable-source criterion is a research shortcut; the panel's own evidence is not re-examined here."],
                )
            elif ev.evidence_type == "prior_classification" and ev.direction == "neutral":
                propose(
                    "An earlier submission did not assert pathogenicity, indicating uncertainty about disease association.",
                    [ev.id],
                    None,
                    0.5,
                    ["The earlier submitter had access to comparable evidence."],
                )
            elif ev.evidence_type == "in_silico" and ev.direction == "benign":
                propose(
                    "Computational predictors agree the change is tolerated.",
                    [ev.id],
                    "BP4",
                    0.65,
                )
            elif ev.evidence_type == "functional" and ev.direction == "benign":
                propose(
                    "Well-established functional assays show no damaging effect.",
                    [ev.id],
                    "BS3",
                    0.7,
                )
        return candidates


class LLMBenignCounsel:
    name = "benign_counsel"

    def __init__(self, provider: ModelProvider):
        self.provider = provider
        self.fallback = MockBenignCounsel()
        self.last_source = "llm"

    async def run(self, state: EvidenceState, opponent: list[AgentClaim] | None = None) -> list[AgentClaim]:
        try:
            result = await self.provider.generate(
                prompts.counsel_system("benign"), prompts.counsel_user(state, opponent or []), ClaimList
            )
            self.last_source = provider_source(self.provider)
            claims = sanitize_claims(result.claims, state, self.name)
            valid = {c.id for c in opponent or []}
            return [c.model_copy(update={"rebuts": c.rebuts if c.rebuts in valid else None}) for c in claims]
        except Exception as e:  # noqa: BLE001
            log.warning("%s LLM failed (%s); using deterministic fallback", self.name, e)
            self.last_source = "fallback(mock)"
            return await self.fallback.run(state, opponent)
