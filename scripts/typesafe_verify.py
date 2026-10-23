"""Audit finished cases with TypeSafe Jev: does the cited evidence actually back each claim and verdict?

Usage:  uv run python scripts/typesafe_verify.py [--db variantcourt.db] [--limit 100] [--out typesafe_audit.csv]

Follows TypeSafe's citation-check pattern: one Choice per claim (supports / contradicts /
says_nothing) over that claim's cited evidence, plus one for the final verdict over all evidence.
Compares Jev with the court's own accept/reject decisions. Answers below AUTO_ACCEPT confidence
go to human review. Needs TYPESAFE_API_KEY in .env.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import httpx
from dotenv import load_dotenv

API = "https://api.typesafe.ai/v1/systemone"
AUTO_ACCEPT = 0.8  # ponytail: cookbook default, tune on reviewed cases
RELATION = {
    "supports": "The evidence states the claim or directly implies that it is true",
    "contradicts": "The evidence states the opposite of the claim or implies it is false",
    "says_nothing": "The evidence does not address what the claim asserts, either way",
}
VERDICT_CLAIM = {
    "path": "This DNA variant is likely to cause disease (pathogenic).",
    "benign": "This DNA variant is likely harmless (benign).",
    "abstain": "The evidence is mixed or too thin to tell whether this DNA variant causes disease.",
}


def bucket(label: str) -> str:
    s = label.lower()
    if "uncertain" in s or "conflicting" in s or s in ("vus", "needs_review", "insufficient evidence"):
        return "abstain"
    return "path" if "pathogenic" in s else "benign" if "benign" in s else "abstain"


def audit_case(client: httpx.Client, key: str, case: dict) -> list[dict]:
    st, verdict = case["result"]["state"], case["result"]["verdict"]
    evidence = {e["id"]: f"{e['source']}: {e['summary']}" for e in st["evidence_items"]}
    claims = st["pathogenic_claims"] + st["benign_claims"]
    questions = {
        c["id"]: {
            "type": "choice",
            "instructions": f"Variant `variant`. How does the evidence cited for this claim ({', '.join(f'`evidence.{i}`' for i in c['evidence_ids'] if i in evidence) or 'none'}) relate to the claim: \"{c['claim']}\"",
            "criteria": RELATION,
        }
        for c in claims
    }
    questions["verdict"] = {
        "type": "choice",
        "instructions": f"Taking all items in `evidence` together, how do they relate to the claim: \"{VERDICT_CLAIM[bucket(verdict['classification'])]}\"",
        "criteria": RELATION,
    }
    r = client.post(API, headers={"Authorization": f"Bearer {key}"}, json={
        "model": "jev-latest",
        "state": {"variant": st["variant"]["input"], "evidence": evidence},
        "questions": questions,
    })
    r.raise_for_status()
    answers = r.json()["answers"]
    rows = []
    for c in claims + [{"id": "verdict", "claim": verdict["classification"], "agent": "rule_engine"}]:
        a = answers[c["id"]]
        court = "accept" if c["id"] == "verdict" else st["claim_status"].get(c["id"], "accept")
        # Court and Jev agree when an accepted claim is supported, or a rejected one is not.
        agrees = (a["choice"] == "supports") == (court != "reject")
        rows.append({
            "case_id": case["id"], "variant": st["variant"]["input"], "item": c["id"], "agent": c["agent"],
            "claim": c["claim"], "court": court, "jev": a["choice"], "confidence": round(a["confidence"], 3),
            "agrees_with_court": agrees, "needs_review": a["confidence"] < AUTO_ACCEPT or not agrees,
        })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="variantcourt.db")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--out", default="typesafe_audit.csv")
    args = ap.parse_args()
    load_dotenv(".env")
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if not key:
        raise SystemExit("TYPESAFE_API_KEY is not set in .env")

    db = sqlite3.connect(args.db)
    db.row_factory = sqlite3.Row
    cases = [{"id": r["id"], "result": json.loads(r["result"])} for r in db.execute(
        "SELECT id, result FROM cases WHERE status='completed' ORDER BY created_at DESC LIMIT ?", (args.limit,))]

    rows, failed = [], 0
    with httpx.Client(timeout=60) as client, ThreadPoolExecutor(4) as pool:
        for fut in [pool.submit(audit_case, client, key, c) for c in cases]:
            try:
                rows.extend(fut.result())
            except httpx.HTTPError as e:
                failed += 1
                print("request failed:", str(e)[:120])

    if not rows:
        raise SystemExit("no results")
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    claims = [r for r in rows if r["item"] != "verdict"]
    verdicts = [r for r in rows if r["item"] == "verdict"]
    print(f"audited {len(verdicts)} cases, {len(claims)} claims ({failed} requests failed)")
    print("claims  - Jev says:", dict(Counter(r["jev"] for r in claims)))
    print(f"claims  - Jev agrees with the court's accept/reject: {sum(r['agrees_with_court'] for r in claims)}/{len(claims)}")
    print("verdict - Jev says:", dict(Counter(r["jev"] for r in verdicts)))
    print(f"needs human review: {sum(r['needs_review'] for r in rows)} items")
    for r in [r for r in rows if not r["agrees_with_court"]][:8]:
        print(f"  disagree: {r['variant']} [{r['court']}] Jev={r['jev']} ({r['confidence']}) {r['claim'][:90]}")
    print(f"per-item results -> {args.out}")


if __name__ == "__main__":
    main()
