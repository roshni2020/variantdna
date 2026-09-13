"""On-disk JSON cache for fetched evidence bundles. Keeps the demo alive offline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

DEFAULT_DIR = Path(__file__).resolve().parents[3] / ".cache" / "evidence"


class EvidenceCache:
    def __init__(self, directory: Path | str | None = None):
        self.dir = Path(directory) if directory else DEFAULT_DIR
        self.dir.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        return self.dir / f"{quote(key, safe='')}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        p = self.path(key)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def put(self, key: str, bundle: dict[str, Any]) -> None:
        self.path(key).write_text(json.dumps(bundle, indent=1, default=str), encoding="utf-8")
