"""TypeSafe Cross-Examiner.

TypeSafe attacks both sides every round. The Jury may not update state until it returns.
This module defines the interface and a deterministic mock that implements the same
checks a real TypeSafe prompt is asked to perform, so the demo loop is meaningful
without credentials.
"""

from __future__ import annotations

from typing import Protocol

from variantcourt.domain import AgentClaim, Conflict, CrossExamResult, EvidenceItem, EvidenceState

LOF_CONSEQUENCES = {
    "frameshift_variant",
    "stop_gained",
    "splice_acceptor_variant",
    "splice_donor_variant",
    "start_lost",
}


class TypeSafeProvider(Protocol):
    name: str

    async def cross_examine(
        self,
        state: EvidenceState,
        pathogenic_claims: list[AgentClaim],
        benign_claims: list[AgentClaim],
    ) -> CrossExamResult: ...


def _side(claim: AgentClaim) -> str:
    return "benign" if "benign" in claim.agent else "pathogenic"


class MockTypeSafeProvider:
    """Deterministic cross-examination over structured claims and evidence."""

    name = "typesafe(mock)"

    async def cross_examine(
        self,
        state: EvidenceState,
        pathogenic_claims: list[AgentClaim],
        benign_claims: list[AgentClaim],
    ) -> CrossExamResult:
        evidence = state.evidence_by_id()
        conflicts: list[Conflict] = []
        rejected: set[str] = set()
        weakened: set[str] = set()
        open_questions: list[str] = []
        checks: list[str] = []

        claims = list(pathogenic_claims) + list(benign_claims)
        by_id = {c.id: c for c in claims}

        def add_conflict(ctype: str, claim_ids: list[str], severity: str, description: str) -> None:
            cid = f"cf_{ctype}_{'_'.join(sorted(claim_ids))}"
            if any(c.id == cid for c in conflicts):
                return
            conflicts.append(
                Conflict(
                    id=cid,
                    conflict_type=ctype,
                    description=description,
                    affected_claim_ids=sorted(claim_ids),
                    severity=severity,  # type: ignore[arg-type]
                )
            )

        for claim in claims:
            cited: list[EvidenceItem] = []
            missing = [eid for eid in claim.evidence_ids if eid not in evidence]
            if missing or not claim.evidence_ids:
                add_conflict(
                    "unsupported_citation",
                    [claim.id],
                    "high",
                    f"Claim {claim.id} cites evidence that does not exist: {missing or 'none cited'}.",
                )
                rejected.add(claim.id)
                continue
            cited = [evidence[eid] for eid in claim.evidence_ids]

            # Transcript mismatch: evidence annotated on a different transcript than the variant.
            if state.variant.transcript:
                mismatched = [e for e in cited if e.transcript and e.transcript != state.variant.transcript]
                if mismatched:
                    add_conflict(
                        "transcript_mismatch",
                        [claim.id],
                        "high",
                        f"Claim {claim.id} relies on {', '.join(e.id for e in mismatched)} annotated on "
                        f"{mismatched[0].transcript}, but the case transcript is {state.variant.transcript}.",
                    )
                    rejected.add(claim.id)
                    checks.append(f"Re-annotate {mismatched[0].id} on {state.variant.transcript}")

            # Direction support: does any cited evidence actually point the claim's way?
            side = _side(claim)
            if not any(e.direction == side for e in cited):
                cited_dirs = ", ".join(f"{e.id}={e.direction}" for e in cited)
                if claim.proposed_criterion:
                    add_conflict(
                        "unsupported_claim",
                        [claim.id],
                        "medium",
                        f"Claim {claim.id} proposes {claim.proposed_criterion} for '{side}' but none of its "
                        f"cited evidence points that way ({cited_dirs}).",
                    )
                    rejected.add(claim.id)
                else:
                    add_conflict(
                        "weak_support",
                        [claim.id],
                        "low",
                        f"Claim {claim.id} argues '{side}' from neutral evidence only ({cited_dirs}); "
                        f"it can carry little weight.",
                    )
                    weakened.add(claim.id)

            # Rebuttal that brings no new evidence against the claim it answers.
            target = by_id.get(claim.rebuts) if claim.rebuts else None
            if target is not None and set(claim.evidence_ids) <= set(target.evidence_ids) and claim.id not in rejected:
                add_conflict(
                    "empty_rebuttal",
                    [claim.id],
                    "low",
                    f"Claim {claim.id} answers {target.id} using only the same evidence; it adds nothing.",
                )
                weakened.add(claim.id)

            # Stale evidence.
            stale = [
                e for e in cited
                if e.metadata.get("stale") or (e.metadata.get("submission_year") and e.metadata["submission_year"] < 2015)
            ]
            if stale and claim.id not in rejected:
                add_conflict(
                    "stale_evidence",
                    [claim.id],
                    "low",
                    f"Claim {claim.id} depends on stale evidence {', '.join(e.id for e in stale)} "
                    f"(submitted {stale[0].metadata.get('submission_year', 'unknown')}).",
                )
                weakened.add(claim.id)

            # Overconfidence relative to the evidence itself.
            best = max(e.confidence for e in cited)
            if claim.confidence > best + 0.15 and claim.id not in rejected:
                add_conflict(
                    "overconfident_claim",
                    [claim.id],
                    "low",
                    f"Claim {claim.id} confidence {claim.confidence:.2f} exceeds strongest cited evidence ({best:.2f}).",
                )
                weakened.add(claim.id)
                open_questions.append(f"What justifies confidence {claim.confidence:.2f} for {claim.id}?")

            # Missing prerequisites for PVS1.
            if claim.proposed_criterion == "PVS1" and claim.id not in rejected:
                ok = any(
                    e.metadata.get("consequence") in LOF_CONSEQUENCES and e.metadata.get("lof_mechanism")
                    for e in cited
                )
                if not ok:
                    add_conflict(
                        "missing_prerequisite",
                        [claim.id],
                        "medium",
                        f"PVS1 proposed by {claim.id} without an established loss-of-function mechanism.",
                    )
                    weakened.add(claim.id)

        # Double counting: same criterion proposed twice on one side, or same evidence reused
        # by multiple claims of the same side.
        for side_claims in (pathogenic_claims, benign_claims):
            by_criterion: dict[str, list[AgentClaim]] = {}
            by_evidence: dict[str, list[AgentClaim]] = {}
            for c in side_claims:
                if c.proposed_criterion:
                    by_criterion.setdefault(c.proposed_criterion, []).append(c)
                for eid in c.evidence_ids:
                    by_evidence.setdefault(eid, []).append(c)
            for code, cs in by_criterion.items():
                if len(cs) > 1:
                    ids = [c.id for c in cs]
                    add_conflict(
                        "double_counting",
                        ids,
                        "medium",
                        f"{code} is proposed by {len(cs)} separate claims ({', '.join(ids)}); it can count once.",
                    )
                    for c in cs[1:]:
                        if c.id not in rejected:
                            weakened.add(c.id)
            for eid, cs in by_evidence.items():
                if len(cs) > 1:
                    ids = [c.id for c in cs]
                    add_conflict(
                        "duplicate_evidence_use",
                        ids,
                        "medium" if any(c.proposed_criterion for c in cs) else "low",  # only criteria can be double-counted
                        f"Evidence {eid} is reused by claims {', '.join(ids)} on the same side.",
                    )

        validated = [c.id for c in claims if c.id not in rejected and c.id not in weakened]
        return CrossExamResult(
            contradictions=conflicts,
            rejected_claim_ids=sorted(rejected),
            weakened_claim_ids=sorted(weakened - rejected),
            validated_claim_ids=validated,
            open_questions=open_questions,
            recommended_checks=checks,
            provider=self.name,
        )


class TypeSafeAPIProvider:
    """Real TypeSafe adapter.

    Calls the configured TypeSafe endpoint (OpenAI-compatible chat shape by default) with
    the cross-examination prompt and validates a CrossExamResult. The deterministic checks
    always run too; findings are merged so the loop never depends on a single call
    succeeding. If the API fails, the deterministic result stands and the provider name
    reports the fallback.
    """

    def __init__(self, model_provider, hybrid: bool = True):
        self.model_provider = model_provider
        self.hybrid = hybrid
        self.deterministic = MockTypeSafeProvider()
        self.name = "typesafe"
        self.last_source = "typesafe"

    async def cross_examine(
        self,
        state: EvidenceState,
        pathogenic_claims: list[AgentClaim],
        benign_claims: list[AgentClaim],
    ) -> CrossExamResult:
        from . import prompts

        base = await self.deterministic.cross_examine(state, pathogenic_claims, benign_claims)
        try:
            llm = await self.model_provider.generate(
                prompts.TYPESAFE_SYSTEM,
                prompts.typesafe_user(state, pathogenic_claims, benign_claims),
                CrossExamResult,
            )
        except Exception as e:  # noqa: BLE001
            self.last_source = f"typesafe fallback(deterministic): {e}"
            return base.model_copy(update={"provider": "typesafe(deterministic fallback)"})

        self.last_source = "typesafe"
        claim_ids = {c.id for c in pathogenic_claims + benign_claims}
        merged_conflicts = list(base.contradictions)
        seen = {c.id for c in merged_conflicts}
        for c in llm.contradictions:
            ids = [i for i in c.affected_claim_ids if i in claim_ids]
            if not ids or c.id in seen:
                continue
            seen.add(c.id)
            merged_conflicts.append(c.model_copy(update={"affected_claim_ids": ids, "resolved": False}))
        rejected = set(base.rejected_claim_ids) | {i for i in llm.rejected_claim_ids if i in claim_ids}
        weakened = (set(base.weakened_claim_ids) | {i for i in llm.weakened_claim_ids if i in claim_ids}) - rejected
        validated = [i for i in claim_ids if i not in rejected and i not in weakened]
        return CrossExamResult(
            contradictions=merged_conflicts,
            rejected_claim_ids=sorted(rejected),
            weakened_claim_ids=sorted(weakened),
            validated_claim_ids=sorted(validated),
            open_questions=list(dict.fromkeys(base.open_questions + llm.open_questions)),
            recommended_checks=list(dict.fromkeys(base.recommended_checks + llm.recommended_checks)),
            provider="typesafe" if not self.hybrid else "typesafe+deterministic",
        )
