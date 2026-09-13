"""Weights & Biases Weave tracer.

Every tracer event becomes a Weave op call; round metrics are logged as a per-round op
so the Weave UI shows the trajectory (conflicts, rejected claims, citation validity,
latency) across rounds. Falls back to the in-memory tracer when weave is unavailable or
WANDB_API_KEY is not set, so the courtroom never depends on it.
"""

from __future__ import annotations

import logging
from typing import Any

from .tracing import InMemoryTracer, NullSpan

log = logging.getLogger(__name__)

_initialized: dict[str, bool] = {}


class WeaveTracer(InMemoryTracer):
    def __init__(self, project: str = "variantcourt", api_key: str | None = None, entity: str | None = None):
        super().__init__()
        self.enabled = False
        self.project = f"{entity}/{project}" if entity else project
        project = self.project
        self._ops: dict[str, Any] = {}
        try:
            import weave  # type: ignore

            if api_key:
                import os

                os.environ.setdefault("WANDB_API_KEY", api_key)
            self._weave = weave
            if not _initialized.get(project):
                weave.init(project)
                _initialized[project] = True
                log.info("Weave tracing enabled for project %s", project)
            self.enabled = True
        except Exception as e:  # noqa: BLE001
            log.warning("Weave unavailable (%s); tracing stays in memory", e)
            self._weave = None

    def _op(self, name: str):
        if name not in self._ops:
            def _record(**payload: Any) -> dict[str, Any]:
                return payload

            _record.__name__ = name
            self._ops[name] = self._weave.op(name=f"variantcourt.{name}")(_record)
        return self._ops[name]

    def event(self, name: str, **payload: Any) -> None:
        super().event(name, **payload)
        if self.enabled:
            try:
                self._op(name)(**payload)
            except Exception as e:  # noqa: BLE001
                log.debug("weave event failed: %s", e)

    def round_metrics(self, round_number: int, **metrics: Any) -> None:
        super().round_metrics(round_number, **metrics)
        if self.enabled:
            try:
                self._op("round_metrics")(round_number=round_number, **metrics)
            except Exception as e:  # noqa: BLE001
                log.debug("weave round metrics failed: %s", e)

    def wrap_run(self, fn):
        """Wrap the courtroom run so all events nest under one trace per case."""
        if not self.enabled:
            return fn
        return self._weave.op(name="variantcourt.courtroom.run")(fn)

    def wrap_agents(self, runner) -> None:
        """Turn each agent call into a nested Weave op with structured inputs/outputs.

        The trace tree then reads: courtroom.run -> evidence_clerk -> pathogenic_counsel ->
        benign_counsel -> typesafe_cross_examiner -> jury, per round.
        """
        if not self.enabled:
            return
        targets = [
            (runner.clerk, "build_state", "variantcourt.evidence_clerk"),
            (runner.pathogenic, "run", "variantcourt.pathogenic_counsel"),
            (runner.benign, "run", "variantcourt.benign_counsel"),
            (runner.typesafe, "cross_examine", "variantcourt.typesafe_cross_examiner"),
            (runner.jury, "run", "variantcourt.jury"),
        ]
        for obj, attr, name in targets:
            try:
                fn = getattr(obj, attr)
                if getattr(fn, "_weave_wrapped", False):
                    continue
                wrapped = self._weave.op(name=name)(fn)
                wrapped._weave_wrapped = True  # type: ignore[attr-defined]
                setattr(obj, attr, wrapped)
            except Exception as e:  # noqa: BLE001
                log.debug("could not wrap %s: %s", name, e)
        for agent in (runner.pathogenic, runner.benign, runner.jury):
            provider = getattr(agent, "provider", None)
            if provider is not None and not getattr(provider, "_weave_wrapped", False):
                try:
                    provider.generate = self._weave.op(name=f"variantcourt.llm.{provider.name}")(provider.generate)
                    provider._weave_wrapped = True
                except Exception as e:  # noqa: BLE001
                    log.debug("could not wrap provider: %s", e)

    # ---- Agents dashboard spans: conversation = case, turn = round, tool = agent call
    def conversation(self, case_id: str, variant: str, **attrs: Any):
        if not self.enabled:
            return NullSpan()
        try:
            span = self._weave.start_conversation(
                agent_name="variantcourt",
                conversation_id=case_id,
                conversation_name=f"{variant} ({case_id})",
                continue_parent_trace=True,
                attributes={"variant": variant, **{k: str(v) for k, v in attrs.items()}},
            )
            return span
        except Exception as e:  # noqa: BLE001
            log.debug("conversation span failed: %s", e)
            return NullSpan()


    def agent_turn(self, round_number: int, agent_name: str, prompt: str, model: str = ""):
        if not self.enabled:
            return NullSpan()
        try:
            return _AgentTurn(self._weave, round_number, agent_name, prompt, model)
        except Exception as e:  # noqa: BLE001
            log.debug("agent turn failed: %s", e)
            return NullSpan()


class _AgentTurn:
    """One speaker's contribution to a round: a Weave turn holding an LLM span whose
    output is what the agent said. Renders as a labelled dialogue in Agents > Conversations."""

    def __init__(self, weave_mod, round_number: int, agent_name: str, prompt: str, model: str):
        self.weave = weave_mod
        self.turn = weave_mod.start_turn(user_message=prompt, agent_name=agent_name)
        self.llm = None
        self.model = model or "deterministic"
        self.result = None

    def __enter__(self):
        self.turn.__enter__()
        try:
            from weave.conversation import Message

            self.llm = self.weave.start_llm(model=self.model, provider_name="variantcourt")
            self.llm.__enter__()
            self.llm.input_messages = [Message(role="user", content="(structured EvidenceState; see trace inputs)")]
        except Exception as e:  # noqa: BLE001
            log.debug("llm span failed: %s", e)
            self.llm = None
        return self

    def say(self, text: str) -> None:
        self.result = text
        if self.llm is not None:
            try:
                self.llm.output(text)
            except Exception as e:  # noqa: BLE001
                log.debug("llm output failed: %s", e)

    def __exit__(self, *exc):
        if self.llm is not None:
            try:
                self.llm.__exit__(*exc)
            except Exception:  # noqa: BLE001
                pass
        return self.turn.__exit__(*exc)
