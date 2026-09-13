"""The courtroom loop.

Evidence -> Pathogenic -> Benign -> TypeSafe -> Jury -> reducer, up to MAX_ROUNDS,
then the deterministic rule engine issues the verdict.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from variantcourt.acmg import evaluate_verdict
from variantcourt.agents import (
    CounselAgent,
    EvidenceClerk,
    JuryAgent,
    MockBenignCounsel,
    MockEvidenceClerk,
    MockJury,
    MockPathogenicCounsel,
    MockTypeSafeProvider,
    TypeSafeProvider,
)
from variantcourt.domain import CaseResult, EvidenceState, RoundSnapshot

from .convergence import has_converged
from .reducer import reduce_state
from .tracing import InMemoryTracer, Tracer

MAX_ROUNDS = 3


def _claims_text(claims) -> str:
    return "\n".join(
        f"[{c.proposed_criterion or 'context'} | conf {c.confidence:.2f}]{' in reply to ' + c.rebuts if c.rebuts else ''} {c.claim} (evidence: {', '.join(c.evidence_ids)})"
        for c in claims
    )


def _cross_exam_text(x) -> str:
    lines = [f"Validated {len(x.validated_claim_ids)}, weakened {len(x.weakened_claim_ids)}, rejected {len(x.rejected_claim_ids)}."]
    for c in x.contradictions:
        lines.append(f"[{c.severity.upper()} {c.conflict_type}] {c.description}")
    return "\n".join(lines)


def _jury_text(d) -> str:
    lines = [d.rationale] if d.rationale else []
    for dec in d.claim_decisions:
        lines.append(f"{dec.action.upper()} {dec.claim_id}: {dec.rationale}")
    if d.conflicts_to_resolve:
        lines.append(f"Resolved conflicts: {', '.join(d.conflicts_to_resolve)}")
    return "\n".join(lines) or "No decisions."


@dataclass
class CourtroomConfig:
    max_rounds: int = MAX_ROUNDS
    mode: str = "demo"


@dataclass
class CourtroomRunner:
    clerk: EvidenceClerk = field(default_factory=MockEvidenceClerk)
    pathogenic: CounselAgent = field(default_factory=MockPathogenicCounsel)
    benign: CounselAgent = field(default_factory=MockBenignCounsel)
    typesafe: TypeSafeProvider = field(default_factory=MockTypeSafeProvider)
    jury: JuryAgent = field(default_factory=MockJury)
    tracer: Tracer = field(default_factory=InMemoryTracer)
    config: CourtroomConfig = field(default_factory=CourtroomConfig)

    async def run(self, variant_input: str, case_id: str | None = None) -> CaseResult:
        case_id = case_id or f"case_{uuid.uuid4().hex[:8]}"
        t0 = time.perf_counter()
        self.tracer.event("case_created", case_id=case_id, variant=variant_input, mode=self.config.mode)

        state = await self.clerk.build_state(variant_input)
        self.tracer.event(
            "evidence_retrieved",
            case_id=case_id,
            sources=state.sources_loaded,
            evidence_count=len(state.evidence_items),
            state=state.model_dump(mode="json"),
        )

        snapshots: list[RoundSnapshot] = []
        model_name = getattr(getattr(self.pathogenic, "provider", None), "name", "") or "deterministic"
        conversation = self.tracer.conversation(case_id, variant_input, mode=self.config.mode, max_rounds=self.config.max_rounds)
        conversation.__enter__()
        for round_number in range(1, self.config.max_rounds + 1):
            rt0 = time.perf_counter()

            self.tracer.event("round_started", round=round_number, max_rounds=self.config.max_rounds)

            with self.tracer.agent_turn(round_number, "pathogenic_counsel", f"Round {round_number}, {variant_input}. Pathogenic Counsel, make your case.", model_name) as sp:
                path_claims = await self.pathogenic.run(state, state.benign_claims)
                sp.say(_claims_text(path_claims) or "No evidence-supported pathogenic claims.")
            self.tracer.event(
                "pathogenic_agent",
                round=round_number,
                source=getattr(self.pathogenic, "last_source", "mock"),
                claims=[c.model_dump(mode="json") for c in path_claims],
            )

            with self.tracer.agent_turn(round_number, "benign_counsel", f"Round {round_number}. Benign Counsel, respond.", model_name) as sp:
                ben_claims = await self.benign.run(state, path_claims)
                sp.say(_claims_text(ben_claims) or "No evidence-supported benign claims.")
            self.tracer.event(
                "benign_agent",
                round=round_number,
                source=getattr(self.benign, "last_source", "mock"),
                claims=[c.model_dump(mode="json") for c in ben_claims],
            )

            with self.tracer.agent_turn(round_number, "typesafe_cross_examiner", f"Round {round_number}. TypeSafe, cross-examine both sides.", self.typesafe.name) as sp:
                cross_exam = await self.typesafe.cross_examine(state, path_claims, ben_claims)
                sp.say(_cross_exam_text(cross_exam))
            self.tracer.event(
                "typesafe_cross_exam",
                round=round_number,
                provider=cross_exam.provider,
                result=cross_exam.model_dump(mode="json"),
            )

            # The jury cannot run until TypeSafe has returned (sequential by construction).
            with self.tracer.agent_turn(round_number, "jury", f"Round {round_number}. Jury, rule on the claims.", model_name) as sp:
                jury_delta = await self.jury.run(state, path_claims, ben_claims, cross_exam)
                sp.say(_jury_text(jury_delta))
            self.tracer.event(
                "jury",
                round=round_number,
                source=getattr(self.jury, "last_source", "mock"),
                delta=jury_delta.model_dump(mode="json"),
            )

            new_state, round_result = reduce_state(state, jury_delta, cross_exam, path_claims, ben_claims)

            # A round that still had to reject claims is not a stable round.
            rejected_this_round = any(d.action == "reject" for d in jury_delta.claim_decisions)
            converged = has_converged(state, new_state) and not rejected_this_round
            if converged:
                new_state.converged = True

            known = state.evidence_ids()
            all_claims = path_claims + ben_claims
            valid_citations = sum(
                1 for c in all_claims if c.evidence_ids and all(e in known for e in c.evidence_ids)
            )
            self.tracer.round_metrics(
                round_number,
                number_of_conflicts=len(new_state.unresolved_conflicts()),
                conflicts_added=len(round_result.conflicts_added),
                conflicts_resolved=len(round_result.conflicts_resolved),
                number_of_supported_claims=sum(
                    1 for cid, s in new_state.claim_status.items() if s == "accept"
                ),
                number_of_rejected_claims=len(cross_exam.rejected_claim_ids),
                state_change_score=len(round_result.changes),
                citation_validity=(valid_citations / len(all_claims)) if all_claims else 1.0,
                latency_ms=round((time.perf_counter() - rt0) * 1000, 2),
                converged=converged,
            )

            snapshot = RoundSnapshot(
                round_number=round_number,
                pathogenic_claims=path_claims,
                benign_claims=ben_claims,
                cross_exam=cross_exam,
                jury_delta=jury_delta,
                round_result=round_result,
                state_after=new_state,
            )
            snapshots.append(snapshot)
            self.tracer.event(
                "round_completed",
                round=round_number,
                converged=converged,
                round_result=round_result.model_dump(mode="json"),
                state=new_state.model_dump(mode="json"),
                metrics=getattr(self.tracer, "rounds", {}).get(round_number, {}),
            )
            state = new_state
            with self.tracer.agent_turn(round_number, "court_clerk", f"Round {round_number}. Clerk, record the state change.", "deterministic") as sp:
                sp.say(
                    ("CONVERGED. " if converged else "")
                    + (f"{len(round_result.changes)} changes: " + "; ".join(round_result.changes) if round_result.changes else "No state changes.")
                )
            if converged:
                break

        verdict = evaluate_verdict(state, max_rounds=self.config.max_rounds)
        with self.tracer.agent_turn(state.round, "rule_engine", "Rule engine, deliver the verdict.", "deterministic") as sp:
            met = [f"{c.code} {c.status}" for c in verdict.criteria if c.status not in ("NOT_MET", "NOT_EVALUATED")]
            sp.say(f"{verdict.classification}. Criteria met: {', '.join(met) or 'none'}. Human review: {verdict.requires_human_review}.")
        conversation.__exit__(None, None, None)
        self.tracer.event(
            "verdict",
            case_id=case_id,
            classification=verdict.classification,
            rounds_used=verdict.rounds_used,
            requires_human_review=verdict.requires_human_review,
            latency_ms=round((time.perf_counter() - t0) * 1000, 2),
            verdict=verdict.model_dump(mode="json"),
        )
        return CaseResult(case_id=case_id, state=state, rounds=snapshots, verdict=verdict)
