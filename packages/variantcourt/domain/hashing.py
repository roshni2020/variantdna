"""Deterministic state hashing used by the reducer and convergence checks."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .schemas import EvidenceState

# Fields that must not feed back into the hash.
_EXCLUDED = {"state_hash", "round", "converged"}


def compute_state_hash(state: "EvidenceState") -> str:
    payload = state.model_dump(mode="json", exclude=_EXCLUDED)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
