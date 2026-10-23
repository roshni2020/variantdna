import asyncio
import os
import sys
from pathlib import Path

import pytest

os.environ["VARIANTCOURT_DB"] = ":memory:"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "api"))

from httpx import ASGITransport, AsyncClient  # noqa: E402

import main as api  # noqa: E402


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=api.app), base_url="http://test") as c:
        yield c


async def _wait(c, case_id, timeout=10.0):
    for _ in range(int(timeout / 0.05)):
        r = await c.get(f"/v1/cases/{case_id}")
        if r.json()["status"] in ("completed", "failed"):
            return r.json()
        await asyncio.sleep(0.05)
    raise AssertionError("case did not finish")


@pytest.mark.asyncio
async def test_health_and_config(client):
    assert (await client.get("/health")).json()["ok"] is True
    cfg = (await client.get("/v1/config")).json()
    assert cfg["mode"] == "demo"
    assert "typesafe" in cfg


@pytest.mark.asyncio
async def test_case_lifecycle_and_stream(client):
    r = await client.post("/v1/cases", json={"variant": "NM_007294.4:c.68_69delAG"})
    assert r.status_code == 201
    case_id = r.json()["id"]
    case = await _wait(client, case_id)
    assert case["status"] == "completed"
    assert case["result"]["verdict"]["classification"] == "Pathogenic"

    verdict = (await client.get(f"/v1/cases/{case_id}/verdict")).json()
    assert verdict["classification"] == "Pathogenic"
    rounds = (await client.get(f"/v1/cases/{case_id}/rounds")).json()
    assert len(rounds) == 2
    evidence = (await client.get(f"/v1/cases/{case_id}/evidence")).json()
    assert len(evidence["evidence_items"]) == 7

    events = (await client.get(f"/v1/cases/{case_id}/events")).json()
    names = [e["name"] for e in events]
    for expected in ("case_created", "evidence_retrieved", "pathogenic_agent", "benign_agent", "typesafe_cross_exam", "jury", "round_completed", "verdict", "case_completed"):
        assert expected in names
    ts = next(e for e in events if e["name"] == "typesafe_cross_exam")
    assert ts["payload"]["result"]["rejected_claim_ids"]

    # SSE replay of a finished case terminates.
    async with client.stream("GET", f"/v1/cases/{case_id}/stream") as resp:
        body = b""
        async for chunk in resp.aiter_bytes():
            body += chunk
    assert b"event: case_completed" in body


@pytest.mark.asyncio
async def test_research_analysis_and_experiment(client):
    r = await client.post("/v1/research/experiment", json={"max_rounds": 3})
    ids = r.json()["case_ids"]
    for cid in ids:
        await _wait(client, cid)
    r = await client.post("/v1/research/experiment", json={"max_rounds": 5})
    for cid in r.json()["case_ids"]:
        await _wait(client, cid)
    analysis = (await client.get("/v1/research/analysis")).json()
    rec = analysis["recommendation"]
    assert rec["runs_analyzed"] >= 6
    assert rec["recommended_config"]["max_rounds"] in (3, 5)
    assert rec["observed"] and rec["hypothesis"] and rec["recommended_experiment"]


@pytest.mark.asyncio
async def test_input_limits_and_orphan_cleanup(client):
    assert (await client.get("/v1/cases?limit=5000")).status_code == 422
    assert (await client.get("/v1/lookup?variant=" + "A" * 500)).status_code == 422
    assert (await client.post("/v1/research/experiment", json={"variants": ["x"] * 50})).status_code == 422
    cid = "case_orphan"
    api.store.create_case(cid, "NM_007294.4:c.68_69delAG", {"max_rounds": 1})
    api.store.set_status(cid, "running")
    assert api.store.fail_orphans() >= 1
    assert api.store.get_case(cid)["status"] == "failed"


@pytest.mark.asyncio
async def test_security_headers(client):
    h = (await client.get("/health")).headers
    assert "frame-ancestors 'none'" in h["content-security-policy"]
    assert "unsafe-inline" not in h["content-security-policy"].split("script-src")[1].split(";")[0]
    assert h["strict-transport-security"].startswith("max-age=")
    assert h["x-content-type-options"] == "nosniff"
