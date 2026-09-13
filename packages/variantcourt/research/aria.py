"""ARIA: the outer research loop.

ARIA is not a courtroom agent. It looks across many VariantCourt runs and recommends a
better loop configuration. This module defines the adapter interface, a local analyzer
that computes real statistics over stored runs (used when ARIA credentials are absent),
ARIA itself runs inside W&B over the runs we log.
"""

from __future__ import annotations

import logging
import statistics
from collections import defaultdict
from typing import Protocol

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)


class RunRecord(BaseModel):
    """Compact summary of one courtroom run; what ARIA reasons over."""

    case_id: str
    variant: str
    max_rounds: int
    typesafe_enabled: bool = True
    rounds_used: int
    converged: bool
    classification: str
    requires_human_review: bool
    conflicts_total: int
    conflicts_unresolved: int
    conflicts_unresolved_high: int
    rejected_claims_round1: int
    rejected_claims_last: int
    citation_validity_mean: float
    latency_ms: float
    provider: str = "mock"


class Recommendation(BaseModel):
    runs_analyzed: int
    observed: str
    hypothesis: str
    recommended_experiment: str
    expected_improvement: str
    recommended_config: dict = Field(default_factory=dict)
    evidence: dict = Field(default_factory=dict)
    source: str = "local"


class ResearchOptimizer(Protocol):
    name: str

    async def analyze(self, runs: list[RunRecord]) -> Recommendation: ...


def _group(runs: list[RunRecord]) -> dict[int, list[RunRecord]]:
    g: dict[int, list[RunRecord]] = defaultdict(list)
    for r in runs:
        g[r.max_rounds].append(r)
    return dict(g)


def _mean(xs: list[float]) -> float:
    return round(statistics.fmean(xs), 3) if xs else 0.0


def analyze_runs(runs: list[RunRecord]) -> Recommendation:
    """Deterministic analysis: compare max_rounds configurations and TypeSafe on/off."""
    if not runs:
        return Recommendation(
            runs_analyzed=0,
            observed="No completed runs yet.",
            hypothesis="Run a few cases with different max_rounds settings to give ARIA something to compare.",
            recommended_experiment="Run the demo variants with max_rounds = 3 and max_rounds = 5.",
            expected_improvement="Enough data to measure whether extra rounds reduce conflicts.",
            recommended_config={"max_rounds": 3},
        )

    by_cfg = _group([r for r in runs if r.typesafe_enabled] or runs)  # ablation cells must not pollute the rounds comparison
    stats = {
        k: {
            "runs": len(v),
            "latency_ms": _mean([r.latency_ms for r in v]),
            "rounds_used": _mean([r.rounds_used for r in v]),
            "unresolved_conflicts": _mean([r.conflicts_unresolved for r in v]),
            "unresolved_high": _mean([r.conflicts_unresolved_high for r in v]),
            "converged_rate": _mean([1.0 if r.converged else 0.0 for r in v]),
            "review_rate": _mean([1.0 if r.requires_human_review else 0.0 for r in v]),
            "citation_validity": _mean([r.citation_validity_mean for r in v]),
        }
        for k, v in by_cfg.items()
    }

    # TypeSafe effect, if both settings exist.
    with_ts = [r for r in runs if r.typesafe_enabled]
    without_ts = [r for r in runs if not r.typesafe_enabled]
    typesafe_note = ""
    if with_ts and without_ts:
        caught = _mean([r.rejected_claims_round1 for r in with_ts])
        surfaced = _mean([r.conflicts_total for r in with_ts])
        typesafe_note = (
            f" With TypeSafe off, every claim was accepted unchallenged; with TypeSafe on, {caught} unsupported "
            f"claims per run were rejected in round 1 and {surfaced} contradictions were surfaced for the jury."
        )

    rejection_drop = _mean([r.rejected_claims_round1 - r.rejected_claims_last for r in runs])

    if len(stats) < 2:
        (cfg, s), = stats.items()
        return Recommendation(
            runs_analyzed=len(runs),
            observed=(
                f"All {len(runs)} runs used max_rounds = {cfg}: mean {s['rounds_used']} rounds used, "
                f"{s['converged_rate']:.0%} converged, {s['unresolved_high']} unresolved high-severity conflicts, "
                f"rejected claims fell by {rejection_drop} between the first and last round.{typesafe_note}"
            ),
            hypothesis=(
                "Rounds after convergence add latency without changing the verdict; a lower cap may be sufficient."
                if s["converged_rate"] >= 0.8 and s["rounds_used"] < cfg
                else "Some cases are stopping on the round cap; a higher cap may resolve remaining conflicts."
            ),
            recommended_experiment=(
                f"Run the same cases with max_rounds = {max(2, cfg - 1) if s['converged_rate'] >= 0.8 and s['rounds_used'] < cfg else cfg + 2}."
            ),
            expected_improvement="Lower latency with equal criterion agreement, or fewer NEEDS_REVIEW outcomes.",
            recommended_config={"max_rounds": max(2, cfg - 1) if s["converged_rate"] >= 0.8 and s["rounds_used"] < cfg else cfg + 2},
            evidence={"by_max_rounds": stats},
        )

    # Pick the config with the fewest unresolved high conflicts, then lowest latency.
    best = sorted(stats.items(), key=lambda kv: (kv[1]["unresolved_high"], kv[1]["review_rate"], kv[1]["latency_ms"]))[0][0]
    worst = max((k for k in stats if k != best), key=lambda k: stats[k]["latency_ms"])
    b, w = stats[best], stats[worst]
    same_quality = abs(b["unresolved_high"] - w["unresolved_high"]) < 0.05 and abs(b["review_rate"] - w["review_rate"]) < 0.05
    observed = (
        f"max_rounds = {worst} runs took {w['latency_ms']:.0f} ms on average versus {b['latency_ms']:.0f} ms for "
        f"max_rounds = {best}, with {'the same' if same_quality else 'different'} unresolved high-severity "
        f"conflicts ({w['unresolved_high']} vs {b['unresolved_high']}).{typesafe_note}"
    )
    if same_quality and best < worst:
        hypothesis = f"The system stabilizes by round {best}; later rounds are loops without progress."
    elif same_quality:
        hypothesis = f"max_rounds = {best} and {worst} reach the same outcome; the shorter cap is cheaper."
    else:
        hypothesis = f"Extra rounds are resolving conflicts that a {min(best, worst)}-round cap leaves open."
    return Recommendation(
        runs_analyzed=len(runs),
        observed=observed,
        hypothesis=hypothesis,
        recommended_experiment=f"Run the full case set with max_rounds = {best} and compare criterion agreement.",
        expected_improvement=(
            f"About {max(0.0, w['latency_ms'] - b['latency_ms']):.0f} ms lower latency per case with similar or better "
            "criterion agreement."
        ),
        recommended_config={"max_rounds": best},
        evidence={"by_max_rounds": stats, "rejected_claims_drop_first_to_last": rejection_drop},
    )


class LocalResearchOptimizer:
    name = "aria(local)"

    async def analyze(self, runs: list[RunRecord]) -> Recommendation:
        rec = analyze_runs(runs)
        rec.source = self.name
        return rec


def build_optimizer() -> ResearchOptimizer:
    # ponytail: ARIA has no HTTP API (it lives in the W&B UI); the local analyzer is the only implementation.
    return LocalResearchOptimizer()
