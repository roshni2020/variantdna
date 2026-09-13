"""Tracer that forwards every event to a callback (used by the API to stream SSE)."""

from __future__ import annotations

from typing import Any, Callable

from .tracing import InMemoryTracer


class StreamingTracer(InMemoryTracer):
    def __init__(self, on_event: Callable[[str, dict[str, Any]], None], inner=None):
        super().__init__()
        self.on_event = on_event
        self.inner = inner  # optional second tracer (e.g. Weave)

    def event(self, name: str, **payload: Any) -> None:
        super().event(name, **payload)
        if self.inner is not None:
            self.inner.event(name, **payload)
        self.on_event(name, payload)

    def round_metrics(self, round_number: int, **metrics: Any) -> None:
        super().round_metrics(round_number, **metrics)
        if self.inner is not None:
            self.inner.round_metrics(round_number, **metrics)
        self.on_event("round_metrics", {"round": round_number, **metrics})

    def conversation(self, case_id: str, variant: str, **attrs: Any):
        if self.inner is not None:
            return self.inner.conversation(case_id, variant, **attrs)
        return super().conversation(case_id, variant, **attrs)

    def agent_turn(self, round_number: int, agent_name: str, prompt: str, model: str = ""):
        if self.inner is not None:
            return self.inner.agent_turn(round_number, agent_name, prompt, model)
        return super().agent_turn(round_number, agent_name, prompt, model)
