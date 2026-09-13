"""Tracing interface. Phase 1 ships an in-memory tracer; Weave adapter comes later."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class NullSpan:
    """No-op span; accepts attribute assignment so callers can set .result freely."""

    result: Any = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def set_attributes(self, attrs: dict[str, Any]):
        return self

    def say(self, text: str) -> None:
        self.result = text


class Tracer(Protocol):
    def event(self, name: str, **payload: Any) -> None: ...

    def round_metrics(self, round_number: int, **metrics: Any) -> None: ...

    def conversation(self, case_id: str, variant: str, **attrs: Any): ...

    def agent_turn(self, round_number: int, agent_name: str, prompt: str, model: str = ""): ...


@dataclass
class InMemoryTracer:
    rounds: dict[int, dict[str, Any]] = field(default_factory=dict)

    def event(self, name: str, **payload: Any) -> None:  # noqa: D401 - no-op sink; subclasses forward
        pass

    def round_metrics(self, round_number: int, **metrics: Any) -> None:
        self.rounds.setdefault(round_number, {}).update(metrics)

    def conversation(self, case_id: str, variant: str, **attrs: Any):
        return NullSpan()

    def agent_turn(self, round_number: int, agent_name: str, prompt: str, model: str = ""):
        return NullSpan()
