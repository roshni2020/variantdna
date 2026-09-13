"""Weave Evaluation of the VariantCourt loop.

Runs the full courtroom on a small labelled set and scores each case on:
- verdict_matches:   classification equals the expert (ClinVar expert panel) label
- citations_valid:   every claim in every round cites only evidence that exists
- converged:         the loop stopped on stability, not on the round cap
- rejections_fall:   fewer rejected claims in the last round than in round 1 (or none at all)

Results land under Evals in the W&B project, next to the traces and runs.

Run:  uv run python evals/weave_eval.py [--rounds 3] [--fixtures]
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages"))

import weave  # noqa: E402

from variantcourt.factory import build_runner  # noqa: E402
from variantcourt.providers import Settings  # noqa: E402

DATASET = [
    {"variant": "NM_007294.4:c.68_69delAG", "expected": "Pathogenic", "note": "BRCA1 185delAG founder mutation; ClinVar expert panel: Pathogenic"},
    {"variant": "NM_007294.4:c.4837A>G", "expected": "Benign", "note": "BRCA1 p.Ser1613Gly; ClinVar expert panel: Benign"},
    {"variant": "NM_000546.6:c.524G>A", "expected": "Pathogenic", "note": "TP53 p.Arg175His hotspot; expected to abstain or flag review with current rules"},
    {"variant": "NM_000000.1:c.1A>G", "expected": "Insufficient Evidence", "note": "Unknown variant; the court must abstain"},
]


class VariantCourtModel(weave.Model):
    max_rounds: int = 3
    mode: str = "live"

    @weave.op
    async def predict(self, variant: str) -> dict:
        runner = build_runner(Settings.from_env(), max_rounds=self.max_rounds)
        result = await runner.run(variant)
        rounds = result.rounds
        known = result.state.evidence_ids()
        all_claims = [c for s in rounds for c in s.pathogenic_claims + s.benign_claims]
        return {
            "classification": result.verdict.classification,
            "requires_human_review": result.verdict.requires_human_review,
            "rounds_used": result.verdict.rounds_used,
            "converged": result.state.converged,
            "rejected_round1": len(rounds[0].cross_exam.rejected_claim_ids) if rounds else 0,
            "rejected_last": len(rounds[-1].cross_exam.rejected_claim_ids) if rounds else 0,
            "claims_total": len(all_claims),
            "claims_with_valid_citations": sum(1 for c in all_claims if c.evidence_ids and set(c.evidence_ids) <= known),
            "unresolved_high": len(result.state.unresolved_conflicts("high")),
            "sources": result.state.sources_loaded,
        }


@weave.op
def verdict_matches(expected: str, output: dict) -> dict:
    return {"verdict_matches": output["classification"] == expected}


@weave.op
def abstained_when_unsure(expected: str, output: dict) -> dict:
    # Abstaining (VUS / Insufficient / NEEDS_REVIEW with review flag) is acceptable; a wrong confident call is not.
    c = output["classification"]
    confident = c in ("Pathogenic", "Likely Pathogenic", "Benign", "Likely Benign")
    return {"no_confident_error": (not confident) or c == expected or c.split()[-1] == expected.split()[-1]}


@weave.op
def citations_valid(output: dict) -> dict:
    return {"citations_valid": output["claims_total"] == output["claims_with_valid_citations"]}


@weave.op
def converged(output: dict) -> dict:
    return {"converged": bool(output["converged"])}


@weave.op
def rejections_fall(output: dict) -> dict:
    return {"rejections_fall": output["rejected_last"] <= output["rejected_round1"] and output["rejected_last"] == 0}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--fixtures", action="store_true", help="use fixture evidence + deterministic agents")
    args = ap.parse_args()
    if args.fixtures:
        os.environ["EVIDENCE_MODE"] = "fixtures"
        os.environ["VARIANTCOURT_MODE"] = "demo"
    s = Settings.from_env()
    if not s.has_weave:
        print("WANDB_API_KEY not set; put it in .env")
        sys.exit(1)
    weave.init(f"{s.wandb_entity}/{s.wandb_project}" if s.wandb_entity else s.wandb_project)
    model = VariantCourtModel(max_rounds=args.rounds, mode="demo" if args.fixtures else s.mode)
    evaluation = weave.Evaluation(
        name=f"variantcourt-loop-eval-r{args.rounds}-{'fixtures' if args.fixtures else 'live'}",
        dataset=weave.Dataset(name="variantcourt-demo-cases", rows=DATASET),
        scorers=[verdict_matches, abstained_when_unsure, citations_valid, converged, rejections_fall],
    )
    summary = await evaluation.evaluate(model)
    print(summary)


if __name__ == "__main__":
    asyncio.run(main())
