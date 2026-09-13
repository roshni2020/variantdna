"""Seed the API database with runs across configurations so ARIA has something to compare.

Usage:  uv run python scripts/seed_runs.py [--api http://127.0.0.1:8000]
Runs the demo variants with max_rounds 3 and 5, TypeSafe on, plus one TypeSafe-off ablation.
"""

from __future__ import annotations

import argparse
import time

import httpx

VARIANTS = ["NM_007294.4:c.68_69delAG", "NM_007294.4:c.4837A>G", "NM_000000.1:c.1A>G"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    args = ap.parse_args()
    ids: list[str] = []
    with httpx.Client(base_url=args.api, timeout=30) as c:
        for max_rounds, ts in ((3, True), (5, True), (3, False)):
            for v in VARIANTS:
                r = c.post("/v1/cases", json={"variant": v, "max_rounds": max_rounds, "typesafe_enabled": ts})
                r.raise_for_status()
                ids.append(r.json()["id"])
        print(f"started {len(ids)} cases")
        pending = set(ids)
        while pending:
            time.sleep(0.5)
            for cid in list(pending):
                st = c.get(f"/v1/cases/{cid}").json()["status"]
                if st in ("completed", "failed"):
                    pending.discard(cid)
        rec = c.get("/v1/research/analysis").json()["recommendation"]
        print("ARIA runs analyzed:", rec["runs_analyzed"])
        print("Observed:", rec["observed"])
        print("Hypothesis:", rec["hypothesis"])
        print("Recommended:", rec["recommended_experiment"])
        print("Expected:", rec["expected_improvement"])


if __name__ == "__main__":
    main()
