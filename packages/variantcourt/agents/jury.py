"""Judge / Jury: turns claims + cross-examination into a structured JuryDelta.

MockJury: deterministic (DEMO MODE). LLMJury: model-backed with hard guard-rails
(cross-examiner rejections are binding, only known ids may be referenced).

The Jury never issues the final classification and never mutates state itself.
"""

from __future__ import annotations

import logging

from variantcourt.providers.base import ModelProvider

from . import prompts
from ._llm_common import provider_source
from variantcourt.domain import (
    AgentClaim,
    ClaimDecision,
    CriterionState,
    CrossExamResult,
    EvidenceState,
    JuryDelta,
)

log = logging.getLogger(__name__)

STRENGTH_BY_PREFIX = [
    ("PVS", "very_strong"),
    ("PS", "strong"),
    ("PM", "moderate"),
    ("PP", "supporting"),
    ("BA", "stand_alone"),
    ("BS", "strong"),
    ("BP", "supporting"),
]


def strength_for(code: str) -> str | None:
    for prefix, strength in STRENGTH_BY_PREFIX:
        if code.startswith(prefix):
            return strength
    return None


class MockJury:
    name = "jury"
    WEAKENED_CAP = 0.35

    async def run(
        self,
        state: EvidenceState,
        pathogenic_claims: list[AgentClaim],
        benign_claims: list[AgentClaim],
        cross_exam: CrossExamResult,
    ) -> JuryDelta:
        claims = pathogenic_claims + benign_claims
        rejected = set(cross_exam.rejected_claim_ids)
        weakened = set(cross_exam.weakened_claim_ids)

        decisions: list[ClaimDecision] = []
        effective_conf: dict[str, float] = {}
        for c in claims:
            if c.id in rejected:
                decisions.append(ClaimDecision(claim_id=c.id, action="reject", rationale="Rejected by cross-examination."))
            elif c.id in weakened:
                new_conf = min(c.confidence, self.WEAKENED_CAP)
                decisions.append(
                    ClaimDecision(
                        claim_id=c.id,
                        action="weaken",
                        rationale="Cross-examination found the claim over-reaches its evidence.",
                        new_confidence=new_conf,
                    )
                )
                effective_conf[c.id] = new_conf
            else:
                decisions.append(ClaimDecision(claim_id=c.id, action="accept", rationale="Supported by cited evidence."))
                effective_conf[c.id] = c.confidence

        # TypeSafe re-examines every claim every round, so any prior conflict it did not
        # raise again this round is treated as resolved.
        raised_now = {c.id for c in cross_exam.contradictions}
        to_resolve = [c.id for c in state.unresolved_conflicts() if c.id not in raised_now]

        # Criterion proposals from surviving claims.
        criteria: dict[str, CriterionState] = {}
        for c in claims:
            if c.id in rejected or not c.proposed_criterion:
                continue
            code = c.proposed_criterion
            status = "WEAKENED" if c.id in weakened else "SUPPORTED"
            existing = criteria.get(code)
            if existing and existing.confidence >= effective_conf[c.id]:
                continue
            criteria[code] = CriterionState(
                code=code,
                status=status,
                strength=strength_for(code),
                evidence_ids=list(c.evidence_ids),
                confidence=round(effective_conf[c.id], 3),
            )

        path_weight = sum(effective_conf[c.id] for c in pathogenic_claims if c.id in effective_conf)
        ben_weight = sum(effective_conf[c.id] for c in benign_claims if c.id in effective_conf)
        total = path_weight + ben_weight
        confidence_score = round(path_weight / total, 3) if total else 0.0

        unresolved_high_after = [
            c for c in cross_exam.contradictions if c.severity == "high"
        ] or [c for c in state.unresolved_conflicts("high") if c.id not in to_resolve]
        request_another = bool(unresolved_high_after or rejected or to_resolve)

        return JuryDelta(
            claim_decisions=decisions,
            conflicts_to_add=list(cross_exam.contradictions),
            conflicts_to_resolve=to_resolve,
            criterion_updates=list(criteria.values()),
            confidence_score=confidence_score,
            request_another_round=request_another,
            rationale=(
                f"{len(rejected)} rejected, {len(weakened)} weakened, "
                f"{len(claims) - len(rejected) - len(weakened)} accepted; "
                f"{len(to_resolve)} conflict(s) resolved."
            ),
        )


class LLMJury:
    name = "jury"

    def __init__(self, provider: ModelProvider):
        self.provider = provider
        self.fallback = MockJury()
        self.last_source = "llm"

    async def run(
        self,
        state: EvidenceState,
        pathogenic_claims: list[AgentClaim],
        benign_claims: list[AgentClaim],
        cross_exam: CrossExamResult,
    ) -> JuryDelta:
        try:
            delta = await self.provider.generate(
                prompts.JURY_SYSTEM,
                prompts.jury_user(state, pathogenic_claims, benign_claims, cross_exam),
                JuryDelta,
            )
            self.last_source = provider_source(self.provider)
            return self._sanitize(delta, state, pathogenic_claims + benign_claims, cross_exam)
        except Exception as e:  # noqa: BLE001
            log.warning("jury LLM failed (%s); using deterministic fallback", e)
            self.last_source = "fallback(mock)"
            return await self.fallback.run(state, pathogenic_claims, benign_claims, cross_exam)

    @staticmethod
    def _sanitize(
        delta: JuryDelta, state: EvidenceState, claims: list[AgentClaim], cross_exam: CrossExamResult
    ) -> JuryDelta:
        claim_ids = {c.id for c in claims}
        raised_now = {c.id for c in cross_exam.contradictions}
        known_conflicts = {c.id for c in state.conflicts} - raised_now  # never resolve what was just raised
        decisions = [d for d in delta.claim_decisions if d.claim_id in claim_ids]
        decided = {d.claim_id for d in decisions}
        # Cross-examiner rejections are binding: the jury cannot quietly accept them.
        for cid in cross_exam.rejected_claim_ids:
            if cid in claim_ids and cid not in decided:
                decisions.append(ClaimDecision(claim_id=cid, action="reject", rationale="Rejected by cross-examination."))
        for d in decisions:
            if d.claim_id in cross_exam.rejected_claim_ids and d.action != "reject":
                d.action = "reject"
                d.rationale = "Overridden: rejected by cross-examination."
        add_ids = {c.id for c in delta.conflicts_to_add}
        conflicts_to_add = list(delta.conflicts_to_add) + [c for c in cross_exam.contradictions if c.id not in add_ids]
        return delta.model_copy(
            update={
                "claim_decisions": decisions,
                "conflicts_to_add": conflicts_to_add,
                "conflicts_to_resolve": [c for c in delta.conflicts_to_resolve if c in known_conflicts],
            }
        )
