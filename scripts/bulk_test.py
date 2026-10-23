"""Bulk test: run many real ClinVar variants through the API and score the court against ClinVar.

Usage:  uv run python scripts/bulk_test.py [--n 50] [--genes BRCA1,BRCA2,TP53] [--api http://127.0.0.1:8000]

Pulls ClinVar variants with >=2 review stars, half pathogenic and half benign, submits them all
at once (the server's MAX_CONCURRENT_CASES queues them), then reports throughput, latency,
failures, and agreement with ClinVar. Writes one CSV row per case.
"""

from __future__ import annotations

import argparse
import csv
import re
import statistics
import time
from collections import Counter

import httpx

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
TITLE = re.compile(r"^(N[MR]_\d+\.\d+)\(([A-Za-z0-9\-]+)\):(c\.\S+)")
GOOD_REVIEW = {
    "practice guideline",
    "reviewed by expert panel",
    "criteria provided, multiple submitters, no conflicts",
}


def bucket(label: str) -> str:
    """Pathogenic / Likely pathogenic -> path, Benign / Likely benign -> benign, anything else -> abstain."""
    s = label.lower()
    if "conflicting" in s or "uncertain" in s:
        return "abstain"
    if "pathogenic" in s:
        return "path"
    if "benign" in s:
        return "benign"
    return "abstain"


def clinvar_variants(genes: list[str], n: int) -> list[tuple[str, str]]:
    """[(variant, clinvar label)], balanced pathogenic/benign across genes."""
    per = max(1, n // (2 * len(genes)))
    out: list[tuple[str, str]] = []
    with httpx.Client(timeout=30) as c:
        for gene in genes:
            for sig in ("pathogenic", "benign"):
                ids = c.get(f"{EUTILS}/esearch.fcgi", params={
                    "db": "clinvar", "term": f"{gene}[gene] AND clinsig_{sig}[prop] AND single_gene[prop]",
                    "retmode": "json", "retmax": min(400, max(100, per * 10)),
                }).json()["esearchresult"]["idlist"]
                time.sleep(0.4)  # NCBI allows 3 requests/s without an API key
                if not ids:
                    continue
                res = c.get(f"{EUTILS}/esummary.fcgi", params={"db": "clinvar", "id": ",".join(ids), "retmode": "json"}, timeout=90).json()["result"]
                time.sleep(0.4)
                got = 0
                for uid in res["uids"]:
                    cls = res[uid].get("germline_classification") or {}
                    m = TITLE.match(res[uid].get("title", ""))
                    if m and cls.get("review_status") in GOOD_REVIEW and bucket(cls.get("description", "")) != "abstain":
                        out.append((f"{m.group(1)}:{m.group(3)}", cls["description"]))
                        got += 1
                        if got >= per:
                            break
    return out[:n]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--genes", default="BRCA1,BRCA2,TP53,MLH1,MSH2,ATM,PALB2,CHEK2")
    ap.add_argument("--max-rounds", type=int, default=3)
    ap.add_argument("--out", default="bulk_results.csv")
    args = ap.parse_args()

    variants = clinvar_variants(args.genes.split(","), args.n)
    print(f"collected {len(variants)} ClinVar variants (>=2 stars)")

    t0 = time.time()
    with httpx.Client(base_url=args.api, timeout=60) as c:
        expected: dict[str, tuple[str, str]] = {}
        for v, label in variants:
            r = c.post("/v1/cases", json={"variant": v, "max_rounds": args.max_rounds})
            r.raise_for_status()
            expected[r.json()["id"]] = (v, label)
        print(f"submitted {len(expected)} cases")

        pending = set(expected)
        while pending:
            time.sleep(2)
            statuses = {x["id"]: x["status"] for x in c.get("/v1/cases", params={"limit": 200}).json()}
            pending = {cid for cid in pending if statuses.get(cid) not in ("completed", "failed")}
            print(f"  {len(expected) - len(pending)}/{len(expected)} done ({time.time() - t0:.0f}s)", end="\r")
        wall = time.time() - t0
        print()

        rows = []
        for cid, (v, label) in expected.items():
            case = c.get(f"/v1/cases/{cid}").json()
            verdict = (case.get("result") or {}).get("verdict") or {}
            got = verdict.get("classification", "")
            rows.append({
                "case_id": cid, "variant": v, "clinvar": label, "status": case["status"], "verdict": got,
                "agrees": bucket(got) == bucket(label), "abstained": case["status"] == "completed" and bucket(got) == "abstain",
                "wrong_side": bucket(got) not in ("abstain", bucket(label)) and case["status"] == "completed",
                "rounds": verdict.get("rounds_used"), "queued_s": round((case.get("started_at") or t0) - case["created_at"], 1),
                "run_s": round((case.get("finished_at") or 0) - (case.get("started_at") or 0), 1) if case.get("finished_at") else None,
                "error": case.get("error") or "",
            })

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    done = [r for r in rows if r["status"] == "completed"]
    run_s = sorted(r["run_s"] for r in done if r["run_s"] is not None)
    print(f"\n{len(rows)} cases in {wall:.0f}s ({len(rows) / wall * 60:.1f} cases/min)")
    print(f"completed {len(done)}, failed {len(rows) - len(done)}")
    if run_s:
        p95 = run_s[min(len(run_s) - 1, int(len(run_s) * 0.95))]
        print(f"run time per case: median {statistics.median(run_s):.1f}s, p95 {p95:.1f}s")
    if done:
        print(f"agrees with ClinVar: {sum(r['agrees'] for r in done)}/{len(done)}")
        print(f"abstained (VUS / needs review / insufficient): {sum(r['abstained'] for r in done)}")
        print(f"WRONG SIDE (called pathogenic as benign or vice versa): {sum(r['wrong_side'] for r in done)}")
        print("verdicts:", dict(Counter(r["verdict"] for r in done)))
    for r in rows:
        if r["wrong_side"]:
            print(f"  wrong side: {r['variant']}  ClinVar={r['clinvar']}  court={r['verdict']}")
    errs = Counter(r["error"][:80] for r in rows if r["error"])
    for e, k in errs.most_common(5):
        print(f"  {k}x error: {e}")
    print(f"per-case results -> {args.out}")


if __name__ == "__main__":
    main()
