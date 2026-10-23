"""Environment-driven provider wiring. Nothing else reads env vars for models."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv

    # Repo-root .env (four levels up from this file); never overrides real env vars.
    load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=False)
    load_dotenv(override=False)
except ImportError:  # pragma: no cover
    pass


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    mode: str = "demo"  # demo | live
    evidence_mode: str = "live"  # live | fixtures
    max_rounds: int = 3
    acmg_scoring: str = "rules"  # rules | points
    coreweave_api_key: str = ""
    coreweave_base_url: str = ""
    coreweave_model: str = ""
    fallback_api_key: str = ""
    fallback_base_url: str = ""
    fallback_model: str = ""
    typesafe_api_key: str = ""
    typesafe_base_url: str = ""
    typesafe_model: str = ""
    wandb_api_key: str = ""
    wandb_project: str = "variantcourt"
    wandb_entity: str = ""
    database_path: str = "variantcourt.db"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            mode=_env("VARIANTCOURT_MODE", "demo").lower() or "demo",
            evidence_mode=_env("EVIDENCE_MODE", "live").lower() or "live",
            max_rounds=int(_env("MAX_ROUNDS", "3") or 3),
            acmg_scoring="points" if _env("ACMG_SCORING").lower() == "points" else "rules",
            coreweave_api_key=_env("COREWEAVE_API_KEY"),
            coreweave_base_url=_env("COREWEAVE_BASE_URL"),
            coreweave_model=_env("COREWEAVE_MODEL", "meta-llama/Llama-3.3-70B-Instruct"),
            fallback_api_key=_env("FALLBACK_API_KEY"),
            fallback_base_url=_env("FALLBACK_BASE_URL"),
            fallback_model=_env("FALLBACK_MODEL", "llama3.1"),
            typesafe_api_key=_env("TYPESAFE_API_KEY"),
            typesafe_base_url=_env("TYPESAFE_BASE_URL") or "https://api.typesafe.ai",
            typesafe_model=_env("TYPESAFE_MODEL") or "jev-latest",
            wandb_api_key=_env("WANDB_API_KEY"),
            wandb_project=_env("WANDB_PROJECT", "variantcourt") or "variantcourt",
            wandb_entity=_env("WANDB_ENTITY"),
            database_path=_env("VARIANTCOURT_DB", "variantcourt.db") or "variantcourt.db",
        )

    @property
    def live(self) -> bool:
        return self.mode == "live"

    @property
    def has_llm(self) -> bool:
        return bool(self.coreweave_base_url or self.fallback_base_url)

    @property
    def has_typesafe(self) -> bool:
        return bool(self.typesafe_api_key)

    @property
    def has_weave(self) -> bool:
        return bool(self.wandb_api_key)


def build_model_provider(s: Settings):
    """CoreWeave first, then the open-model fallback. Returns None when nothing is configured."""
    from .openai_compat import FallbackProvider, OpenAICompatProvider

    providers = []
    if s.coreweave_base_url:
        headers: dict[str, str] = {}
        key = s.coreweave_api_key or None
        if "inference.wandb.ai" in s.coreweave_base_url:
            # W&B Inference (CoreWeave-hosted) authenticates with the W&B key and needs a project header.
            key = key or s.wandb_api_key or None
            if s.wandb_entity:
                headers["OpenAI-Project"] = f"{s.wandb_entity}/{s.wandb_project}"
        providers.append(
            OpenAICompatProvider("coreweave", s.coreweave_base_url, key, s.coreweave_model, extra_headers=headers)
        )
    if s.fallback_base_url:
        fheaders: dict[str, str] = {}
        fkey = s.fallback_api_key or None
        if "inference.wandb.ai" in s.fallback_base_url:
            fkey = fkey or s.wandb_api_key or None
            if s.wandb_entity:
                fheaders["OpenAI-Project"] = f"{s.wandb_entity}/{s.wandb_project}"
        providers.append(
            OpenAICompatProvider("fallback", s.fallback_base_url, fkey, s.fallback_model, extra_headers=fheaders)
        )
    if not providers:
        return None
    return FallbackProvider(providers)
