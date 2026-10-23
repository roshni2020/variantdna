"""Build a CourtroomRunner from Settings. The only place that decides mock vs live."""

from __future__ import annotations

import logging

from variantcourt.agents import (
    LLMBenignCounsel,
    LLMJury,
    LLMPathogenicCounsel,
    LiveEvidenceClerk,
    MockBenignCounsel,
    MockEvidenceClerk,
    MockJury,
    MockPathogenicCounsel,
    MockTypeSafeProvider,
    TypeSafeAPIProvider,
)
from variantcourt.loopcore import CourtroomConfig, CourtroomRunner, InMemoryTracer
from variantcourt.loopcore.weave_tracer import WeaveTracer
from variantcourt.providers import Settings, build_model_provider

log = logging.getLogger(__name__)


def describe(runner: CourtroomRunner) -> dict:
    return {
        "mode": runner.config.mode,
        "max_rounds": runner.config.max_rounds,
        "evidence": getattr(runner.clerk, "name", "?"),
        "pathogenic": getattr(runner.pathogenic, "last_source", None) or runner.pathogenic.__class__.__name__,
        "benign": getattr(runner.benign, "last_source", None) or runner.benign.__class__.__name__,
        "typesafe": runner.typesafe.name,
        "jury": getattr(runner.jury, "last_source", None) or runner.jury.__class__.__name__,
        "tracer": "weave" if getattr(runner.tracer, "enabled", False) else "in-memory",
        "scoring": runner.config.scoring,
    }


def build_runner(settings: Settings | None = None, max_rounds: int | None = None, typesafe_enabled: bool = True) -> CourtroomRunner:
    s = settings or Settings.from_env()
    rounds = max_rounds or s.max_rounds

    tracer = WeaveTracer(s.wandb_project, s.wandb_api_key, s.wandb_entity or None) if s.has_weave else InMemoryTracer()

    model = build_model_provider(s) if s.live else None
    if s.live and model is None:
        log.warning("VARIANTCOURT_MODE=live but no model endpoint configured; agents run as mocks")

    if model is not None:
        pathogenic, benign, jury = LLMPathogenicCounsel(model), LLMBenignCounsel(model), LLMJury(model)
    else:
        pathogenic, benign, jury = MockPathogenicCounsel(), MockBenignCounsel(), MockJury()

    if not typesafe_enabled:
        typesafe = NoOpTypeSafe()
    elif s.live and s.has_typesafe:
        typesafe = TypeSafeAPIProvider(s.typesafe_api_key, s.typesafe_base_url, s.typesafe_model)
    else:
        typesafe = MockTypeSafeProvider()

    runner = CourtroomRunner(
        clerk=LiveEvidenceClerk() if s.evidence_mode == "live" else MockEvidenceClerk(),
        pathogenic=pathogenic,
        benign=benign,
        typesafe=typesafe,
        jury=jury,
        tracer=tracer,
        config=CourtroomConfig(max_rounds=rounds, mode="live" if (s.live and model is not None) else "demo", scoring=s.acmg_scoring),
    )
    if isinstance(tracer, WeaveTracer) and tracer.enabled:
        tracer.wrap_agents(runner)
        runner.run = tracer.wrap_run(runner.run)  # type: ignore[method-assign]
    return runner


class NoOpTypeSafe:
    """Used only for ARIA ablation experiments: 'what happens without cross-examination?'"""

    name = "typesafe(disabled)"

    async def cross_examine(self, state, pathogenic_claims, benign_claims):
        from variantcourt.domain import CrossExamResult

        return CrossExamResult(
            validated_claim_ids=[c.id for c in pathogenic_claims + benign_claims],
            provider=self.name,
        )
