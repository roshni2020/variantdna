"""Provider-neutral model interface.

Adapters to add later: CoreWeave hosted inference, TypeSafe, local/open-model fallback.
Nothing in the app should call a model SDK directly; go through ModelProvider.
"""

from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class ModelProvider(Protocol):
    name: str

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T] | None = None,
    ) -> T | str: ...
