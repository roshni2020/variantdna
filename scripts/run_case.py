"""Run one variant through the VariantCourt loop and print the courtroom transcript.

Usage:
    python scripts/run_case.py "NM_007294.4:c.68_69delAG"
    python scripts/run_case.py "NM_007294.4:c.4837A>G" --rounds 3
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages"))

from variantcourt.loopcore import CourtroomConfig, CourtroomRunner, InMemoryTracer  # noqa: E402


def print_case(result, tracer: InMemoryTracer) -> None:
    s = result.state
    v = s.variant
    print("=" * 72)
    print(f"VARIANTCOURT  case {result.case_id}")
    print(f"Variant: {v.input}   Gene: {v.gene or '?'}   Transcript: {v.transcript or '?'}")
    if s.disease_context and s.disease_context.disease_name:
        print(f"Disease context: {s.disease_context.disease_name}")
    print(f"Sources loaded: {', '.join(s.sources_loaded)}   Evidence items: {len(s.evidence_items)}")
    print("=" * 72)

    for snap in result.rounds:
        r = snap.round_number
        print(f"\n--- ROUND {r} ---")
        print("Pathogenic Counsel:")
        for c in snap.pathogenic_claims:
            print(f"  [{c.id}] {c.proposed_criterion or '-':5} conf={c.confidence:.2f}  {c.claim}  <- {', '.join(c.evidence_ids)}")
        print("Benign Counsel:")
        for c in snap.benign_claims:
            print(f"  [{c.id}] {c.proposed_criterion or '-':5} conf={c.confidence:.2f}  {c.claim}  <- {', '.join(c.evidence_ids)}")
        x = snap.cross_exam
        print(f"TypeSafe Cross-Examiner ({x.provider}):")
        print(f"  OK  {len(x.validated_claim_ids)} claims validated")
        for cf in x.contradictions:
            print(f"  !!  [{cf.severity}] {cf.conflict_type}: {cf.description}")
        for cid in x.rejected_claim_ids:
            print(f"  XX  rejected {cid}")
        for cid in x.weakened_claim_ids:
            print(f"  ~~  weakened {cid}")
        print(f"Jury: {snap.jury_delta.rationale}")
        print("State changes:")
        for ch in snap.round_result.changes:
            print(f"  * {ch}")
        m = tracer.rounds.get(r, {})
        print(
            f"Metrics: unresolved_conflicts={m.get('number_of_conflicts')} "
            f"rejected={m.get('number_of_rejected_claims')} "
            f"citation_validity={m.get('citation_validity'):.2f} "
            f"confidence={snap.state_after.confidence_score:.3f} "
            f"hash {snap.round_result.previous_state_hash} -> {snap.round_result.new_state_hash}"
            + ("  CONVERGED" if snap.state_after.converged else "")
        )

    vd = result.verdict
    print("\n=== VERDICT (deterministic rule engine) ===")
    print(f"Classification: {vd.classification}")
    print(f"Rounds used: {vd.rounds_used}   Converged: {vd.converged}   Requires human review: {vd.requires_human_review}")
    print("Criteria:")
    for c in vd.criteria:
        if c.status not in ("NOT_MET", "NOT_EVALUATED"):
            print(f"  {c.code:5} {c.status:12} {c.rationale}  <- {', '.join(c.evidence_ids)}")
    not_met = [c.code for c in vd.criteria if c.status in ("NOT_MET", "NOT_EVALUATED")]
    if not_met:
        print(f"  not met / not evaluated: {', '.join(not_met)}")
    if vd.unresolved_conflicts:
        print("Unresolved conflicts:")
        for cf in vd.unresolved_conflicts:
            print(f"  [{cf.severity}] {cf.conflict_type}: {cf.description}")
    print(f"\n{vd.disclaimer}")
    print("Research prototype - not for clinical diagnosis")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("variant", nargs="?", default="NM_007294.4:c.68_69delAG")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--json", action="store_true", help="print the full CaseResult as JSON")
    args = parser.parse_args()

    tracer = InMemoryTracer()
    runner = CourtroomRunner(tracer=tracer, config=CourtroomConfig(max_rounds=args.rounds))
    result = await runner.run(args.variant)
    if args.json:
        print(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        print_case(result, tracer)


if __name__ == "__main__":
    asyncio.run(main())
