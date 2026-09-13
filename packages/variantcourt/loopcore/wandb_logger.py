"""Log each courtroom run to Weights & Biases as a run with config + per-round metrics.

This is what makes ARIA work: ARIA (inside W&B) compares runs by their logged config
(max_rounds, typesafe_enabled, provider) and metrics (conflicts, rejected claims, latency,
convergence). Weave handles the per-call traces; this module handles run-level records.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


def log_run_to_wandb(
    record: dict[str, Any],
    round_metrics: dict[int, dict[str, Any]],
    project: str,
    entity: str | None = None,
    api_key: str | None = None,
) -> str | None:
    """Blocking. Returns the run URL or None if W&B is unavailable."""
    try:
        import os

        import wandb

        if api_key:
            os.environ.setdefault("WANDB_API_KEY", api_key)
        os.environ.setdefault("WANDB_SILENT", "true")
        run = wandb.init(
            project=project,
            entity=entity or None,
            name=record["case_id"],
            job_type="courtroom_run",
            group=record["variant"],
            tags=[f"max_rounds={record['max_rounds']}", "typesafe" if record.get("typesafe_enabled", True) else "no_typesafe"],
            config={
                "variant": record["variant"],
                "max_rounds": record["max_rounds"],
                "typesafe_enabled": record.get("typesafe_enabled", True),
                "provider": record.get("provider", "mock"),
            },
            reinit="finish_previous",
        )
        for rn in sorted(round_metrics):
            m = {k: v for k, v in round_metrics[rn].items() if isinstance(v, (int, float, bool))}
            run.log({"round": rn, **m}, step=rn)
        summary_keys = (
            "rounds_used", "converged", "classification", "requires_human_review", "conflicts_total",
            "conflicts_unresolved", "conflicts_unresolved_high", "rejected_claims_round1", "rejected_claims_last",
            "citation_validity_mean", "latency_ms",
        )
        for k in summary_keys:
            run.summary[k] = record.get(k)
        url = run.url
        run.finish()
        return url
    except Exception as e:  # noqa: BLE001
        log.warning("W&B run logging failed: %s", e)
        return None
