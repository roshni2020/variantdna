"""SQLite persistence for cases, events, and run summaries. Stdlib only."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


class Store:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init()

    def _init(self) -> None:
        with self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS cases (
                    id TEXT PRIMARY KEY,
                    variant TEXT NOT NULL,
                    status TEXT NOT NULL,
                    config TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    started_at REAL,
                    finished_at REAL,
                    error TEXT,
                    result TEXT
                );
                CREATE TABLE IF NOT EXISTS events (
                    case_id TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    ts REAL NOT NULL,
                    name TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (case_id, seq)
                );
                CREATE TABLE IF NOT EXISTS runs (
                    case_id TEXT PRIMARY KEY,
                    record TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                """
            )

    # ---- cases
    def create_case(self, case_id: str, variant: str, config: dict[str, Any]) -> dict[str, Any]:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO cases (id, variant, status, config, created_at) VALUES (?, ?, ?, ?, ?)",
                (case_id, variant, "created", json.dumps(config), time.time()),
            )
        return self.get_case(case_id)  # type: ignore[return-value]

    def set_status(self, case_id: str, status: str, error: str | None = None, result: dict | None = None) -> None:
        now = time.time()
        with self._lock, self._conn:
            if status == "running":
                self._conn.execute("UPDATE cases SET status=?, started_at=? WHERE id=?", (status, now, case_id))
            elif status in ("completed", "failed"):
                self._conn.execute(
                    "UPDATE cases SET status=?, finished_at=?, error=?, result=? WHERE id=?",
                    (status, now, error, json.dumps(result) if result is not None else None, case_id),
                )
            else:
                self._conn.execute("UPDATE cases SET status=? WHERE id=?", (status, case_id))

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
        return self._row_to_case(row) if row else None

    def list_cases(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM cases ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [self._row_to_case(r, include_result=False) for r in rows]

    @staticmethod
    def _row_to_case(row: sqlite3.Row, include_result: bool = True) -> dict[str, Any]:
        d = dict(row)
        d["config"] = json.loads(d["config"])
        if include_result:
            d["result"] = json.loads(d["result"]) if d.get("result") else None
        else:
            d.pop("result", None)
        return d

    # ---- events
    def add_event(self, case_id: str, name: str, payload: dict[str, Any]) -> int:
        with self._lock, self._conn:
            seq = self._conn.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM events WHERE case_id=?", (case_id,)).fetchone()[0]
            self._conn.execute(
                "INSERT INTO events (case_id, seq, ts, name, payload) VALUES (?, ?, ?, ?, ?)",
                (case_id, seq, time.time(), name, json.dumps(payload, default=str)),
            )
        return int(seq)

    def list_events(self, case_id: str, after: int = 0) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT seq, ts, name, payload FROM events WHERE case_id=? AND seq>? ORDER BY seq", (case_id, after)
        ).fetchall()
        return [{"seq": r["seq"], "ts": r["ts"], "name": r["name"], "payload": json.loads(r["payload"])} for r in rows]

    # ---- research runs
    def add_run(self, case_id: str, record: dict[str, Any]) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO runs (case_id, record, created_at) VALUES (?, ?, ?)",
                (case_id, json.dumps(record), time.time()),
            )

    def list_runs(self) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT record FROM runs ORDER BY created_at").fetchall()
        return [json.loads(r["record"]) for r in rows]
