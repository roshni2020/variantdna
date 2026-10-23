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


# TypeSafe citation-check pattern: one Choice per claim over the evidence it cites.
RELATION = {
    "supports": "The evidence states the claim or directly implies that it is true",
    "contradicts": "The evidence states the opposite of the claim or implies it is false",
    "says_nothing": "The evidence does not address what the claim asserts, either way",
}
AUTO_ACCEPT = 0.8  # ponytail: TypeSafe cookbook default; below it Jev's answer is ignored, tune on audited cases


class TypeSafeAPIProvider:
    """Real TypeSafe adapter: Jev (System One, https://api.typesafe.ai/v1/systemone) judges
    whether each claim's cited evidence supports, contradicts, or says nothing about it.

    The deterministic checks always run too and Jev's confident findings are added on top:
    contradicted claims are rejected, unaddressed ones weakened. If the API fails, the
    deterministic result stands and the provider name reports the fallback.
    """

    def __init__(self, api_key: str, base_url: str = "https://api.typesafe.ai", model: str = "jev-latest"):
        self.api_key = api_key
        self.url = base_url.rstrip("/") + "/v1/systemone"
        self.model = model
        self.deterministic = MockTypeSafeProvider()
        self.name = f"typesafe({model})"
        self.last_source = self.name

    async def judge(self, state: EvidenceState, claims: list[AgentClaim]) -> dict[str, dict]:
        import httpx

        evidence = {e.id: f"{e.source}: {e.summary}" for e in state.evidence_items}
        questions = {
            c.id: {
                "type": "choice",
                "instructions": "Variant `variant`. How does the evidence cited for this claim ("
                + ", ".join(f"`evidence.{i}`" for i in c.evidence_ids)
                + f') relate to the claim: "{c.claim}"',
                "criteria": RELATION,
            }
            for c in claims
        }
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                self.url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "state": {"variant": state.variant.input, "evidence": evidence}, "questions": questions},
            )
        r.raise_for_status()
        return r.json()["answers"]

    async def cross_examine(
        self,
        state: EvidenceState,
        pathogenic_claims: list[AgentClaim],
        benign_claims: list[AgentClaim],
    ) -> CrossExamResult:
        base = await self.deterministic.cross_examine(state, pathogenic_claims, benign_claims)
        known = state.evidence_by_id()
        # Claims citing missing evidence are already rejected; Jev has nothing to read for them.
        claims = [c for c in pathogenic_claims + benign_claims if c.evidence_ids and all(e in known for e in c.evidence_ids)]
        if not claims:
            return base.model_copy(update={"provider": self.name})
        try:
            answers = await self.judge(state, claims)
        except Exception as e:  # noqa: BLE001
            self.last_source = f"typesafe fallback(deterministic): {e}"
            return base.model_copy(update={"provider": "typesafe(deterministic fallback)"})

        self.last_source = self.name
        conflicts = list(base.contradictions)
        rejected, weakened = set(base.rejected_claim_ids), set(base.weakened_claim_ids)
        for c in claims:
            a = answers.get(c.id) or {}
            conf = a.get("confidence", 0.0)
            if conf < AUTO_ACCEPT:
                continue
            if a.get("choice") == "contradicts":
                rejected.add(c.id)
                conflicts.append(Conflict(
                    id=f"cf_typesafe_contradicts_{c.id}", conflict_type="unsupported_claim", severity="medium",
                    affected_claim_ids=[c.id],
                    description=f"TypeSafe Jev: the evidence cited by {c.id} contradicts it (confidence {conf:.2f}).",
                ))
            elif a.get("choice") == "says_nothing" and c.id not in rejected:
                weakened.add(c.id)
                conflicts.append(Conflict(
                    id=f"cf_typesafe_silent_{c.id}", conflict_type="weak_support", severity="low",
                    affected_claim_ids=[c.id],
                    description=f"TypeSafe Jev: the evidence cited by {c.id} does not address it (confidence {conf:.2f}).",
                ))
        all_ids = [c.id for c in pathogenic_claims + benign_claims]
        return CrossExamResult(
            contradictions=conflicts,
            rejected_claim_ids=sorted(rejected),
            weakened_claim_ids=sorted(weakened - rejected),
            validated_claim_ids=[i for i in all_ids if i not in rejected and i not in weakened],
            open_questions=base.open_questions,
            recommended_checks=base.recommended_checks,
            provider=f"{self.name}+deterministic",
        )
