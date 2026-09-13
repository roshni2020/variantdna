"""OpenAI-compatible chat adapter.

CoreWeave hosted inference, vLLM, Ollama, OpenRouter and most open-model gateways expose
the /v1/chat/completions shape, so one adapter covers "CoreWeave" and "local/open-model
fallback"; only base_url, api_key and model differ.
"""

from __future__ import annotations

import json
import re
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


class ProviderError(RuntimeError):
    pass


class OpenAICompatProvider:
    def __init__(
        self,
        name: str,
        base_url: str,
        api_key: str | None,
        model: str,
        timeout: float = 60.0,
        temperature: float = 0.1,
        max_retries: int = 2,
        extra_headers: dict[str, str] | None = None,
    ):
        self.name = name
        self.extra_headers = extra_headers or {}
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.temperature = temperature
        self.max_retries = max_retries

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json", **self.extra_headers}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    async def _chat(self, messages: list[dict[str, str]], json_mode: bool) -> str:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(f"{self.base_url}/chat/completions", headers=self._headers(), json=body)
        if r.status_code >= 400:
            raise ProviderError(f"{self.name} HTTP {r.status_code}: {r.text[:300]}")
        data = r.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            raise ProviderError(f"{self.name} malformed response: {e}") from e

    @staticmethod
    def _extract_json(text: str) -> dict:
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text.split("\n", 1)[1] if "\n" in text else text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            m = _JSON_BLOCK.search(text)
            if not m:
                raise
            return json.loads(m.group(0))

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T] | None = None,
    ) -> T | str:
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        if response_model is None:
            return await self._chat(messages, json_mode=False)

        schema = json.dumps(response_model.model_json_schema(), indent=0)
        messages[0]["content"] += (
            "\n\nRespond with a single JSON object only, no prose, matching this JSON schema:\n" + schema
        )
        last_err: Exception | None = None
        for attempt in range(self.max_retries + 1):
            text = await self._chat(messages, json_mode=True)
            try:
                return response_model.model_validate(self._extract_json(text))
            except (ValidationError, json.JSONDecodeError) as e:
                last_err = e
                messages.append({"role": "assistant", "content": text})
                messages.append(
                    {"role": "user", "content": f"Your JSON was invalid: {str(e)[:500]}. Return corrected JSON only."}
                )
        raise ProviderError(f"{self.name} failed to produce valid {response_model.__name__}: {last_err}")


class FallbackProvider:
    """Tries providers in order; the first that succeeds wins."""

    def __init__(self, providers: list):
        if not providers:
            raise ValueError("FallbackProvider needs at least one provider")
        self.providers = providers
        self.name = "+".join(p.name for p in providers)
        self.last_used: str | None = None

    async def generate(self, system_prompt: str, user_prompt: str, response_model=None):
        errors = []
        for p in self.providers:
            try:
                out = await p.generate(system_prompt, user_prompt, response_model)
                self.last_used = p.name
                return out
            except Exception as e:  # noqa: BLE001 - any provider failure should fall through
                errors.append(f"{p.name}: {e}")
        raise ProviderError("All providers failed: " + " | ".join(errors))
