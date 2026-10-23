"""VariantCourt API.

POST /v1/cases                      create a case
POST /v1/cases/{id}/run             run it in the background
GET  /v1/cases/{id}                 case + result when complete
GET  /v1/cases/{id}/evidence
GET  /v1/cases/{id}/rounds
GET  /v1/cases/{id}/verdict
GET  /v1/cases/{id}/events          stored events (polling)
GET  /v1/cases/{id}/stream          Server-Sent Events, live agent steps
GET  /v1/cases                      recent cases
GET  /v1/research/analysis          ARIA recommendation over all runs
POST /v1/research/experiment        run the demo set with the recommended config
GET  /v1/config                     which agents/providers are active
GET  /health
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from store import Store  # noqa: E402
from variantcourt.domain import CaseResult  # noqa: E402
from variantcourt.factory import build_runner, describe  # noqa: E402
from variantcourt.loopcore import StreamingTracer  # noqa: E402
from variantcourt.loopcore.wandb_logger import log_run_to_wandb  # noqa: E402
from variantcourt.providers import Settings  # noqa: E402
from variantcourt.research import RunRecord, build_optimizer  # noqa: E402

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("variantcourt.api")

settings = Settings.from_env()
store = Store(settings.database_path)
store.fail_orphans()  # a restart kills in-flight background runs; don't leave them "running" forever
optimizer = build_optimizer()
# Weave logs in once per process with blocking network calls; do it before serving, not on
# the event loop inside the first request (that stalled the loop and dropped connections).
build_runner(settings)

DEMO_VARIANTS = ["NM_007294.4:c.68_69delAG", "NM_007294.4:c.4837A>G", "NM_000000.1:c.1A>G"]
DISCLAIMER = "Research prototype - not for clinical diagnosis"

app = FastAPI(title="VariantCourt API", version="0.2.0", description=DISCLAIMER)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- live event fan-out -------------------------------------------------------------
_subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
_tasks: dict[str, asyncio.Task] = {}
# Each case fans out to live evidence APIs and several LLM calls; cap how many run at once.
_run_slots = asyncio.Semaphore(int(os.environ.get("MAX_CONCURRENT_CASES", "4")))


def _publish(case_id: str, name: str, payload: dict[str, Any]) -> None:
    seq = store.add_event(case_id, name, payload)
    msg = {"seq": seq, "ts": time.time(), "name": name, "payload": payload}
    for q in list(_subscribers.get(case_id, [])):
        q.put_nowait(msg)


# ---- schemas ----------------------------------------------------------------------------
class CreateCase(BaseModel):
    variant: str = Field(min_length=3, max_length=200)
    max_rounds: int | None = Field(default=None, ge=1, le=10)
    typesafe_enabled: bool = True
    run: bool = True


class ExperimentRequest(BaseModel):
    max_rounds: int | None = Field(default=None, ge=1, le=10)
    typesafe_enabled: bool = True
    variants: list[str] | None = Field(default=None, max_length=10)


# ---- helpers ----------------------------------------------------------------------------
def _run_record(case_id: str, result: CaseResult, config: dict[str, Any], tracer: StreamingTracer, latency_ms: float) -> RunRecord:
    rounds = result.rounds
    first = rounds[0].cross_exam if rounds else None
    last = rounds[-1].cross_exam if rounds else None
    validity = [m.get("citation_validity", 1.0) for m in tracer.rounds.values()]
    return RunRecord(
        case_id=case_id,
        variant=result.state.variant.input,
        max_rounds=config["max_rounds"],
        typesafe_enabled=config.get("typesafe_enabled", True),
        rounds_used=result.verdict.rounds_used,
        converged=result.state.converged,
        classification=result.verdict.classification,
        requires_human_review=result.verdict.requires_human_review,
        conflicts_total=len(result.state.conflicts),
        conflicts_unresolved=len(result.state.unresolved_conflicts()),
        conflicts_unresolved_high=len(result.state.unresolved_conflicts("high")),
        rejected_claims_round1=len(first.rejected_claim_ids) if first else 0,
        rejected_claims_last=len(last.rejected_claim_ids) if last else 0,
        citation_validity_mean=round(sum(validity) / len(validity), 3) if validity else 1.0,
        latency_ms=round(latency_ms, 1),
        provider=config.get("provider", "mock"),
    )


async def _execute(case_id: str) -> None:
    async with _run_slots:
        await _execute_inner(case_id)


async def _execute_inner(case_id: str) -> None:
    case = store.get_case(case_id)
    if case is None:
        return
    config = case["config"]
    runner = build_runner(settings, max_rounds=config["max_rounds"], typesafe_enabled=config.get("typesafe_enabled", True))
    inner = runner.tracer  # keeps Weave if configured
    tracer = StreamingTracer(lambda n, p: _publish(case_id, n, p), inner=inner if getattr(inner, "enabled", False) else None)
    runner.tracer = tracer
    config["provider"] = describe(runner)["pathogenic"]
    store.set_status(case_id, "running")
    t0 = time.perf_counter()
    try:
        result = await runner.run(case["variant"], case_id=case_id)
        latency = (time.perf_counter() - t0) * 1000
        record = _run_record(case_id, result, config, tracer, latency)
        store.add_run(case_id, record.model_dump())
        store.set_status(case_id, "completed", result=result.model_dump(mode="json"))
        wandb_url = None
        if settings.has_weave:
            wandb_url = await asyncio.to_thread(
                log_run_to_wandb, record.model_dump(), tracer.rounds, settings.wandb_project,
                settings.wandb_entity or None, settings.wandb_api_key,
            )
        _publish(case_id, "case_completed", {"case_id": case_id, "classification": result.verdict.classification, "wandb_url": wandb_url})
    except Exception as e:  # noqa: BLE001
        log.exception("case %s failed", case_id)
        store.set_status(case_id, "failed", error=str(e))
        # Full traceback stays in the server log; clients get the type and message only.
        _publish(case_id, "case_failed", {"case_id": case_id, "error": f"{type(e).__name__}: {e}"[:300]})
    finally:
        _tasks.pop(case_id, None)


def _start(case_id: str) -> None:
    if case_id in _tasks:
        return
    _tasks[case_id] = asyncio.create_task(_execute(case_id))


def _case_or_404(case_id: str) -> dict[str, Any]:
    case = store.get_case(case_id)
    if case is None:
        raise HTTPException(404, "case not found")
    return case


def _result_or_409(case: dict[str, Any]) -> dict[str, Any]:
    if case["status"] != "completed" or not case.get("result"):
        raise HTTPException(409, f"case is {case['status']}")
    return case["result"]


# ---- routes -----------------------------------------------------------------------------
@app.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "mode": settings.mode, "disclaimer": DISCLAIMER}


@app.get("/v1/lookup")
async def lookup(variant: str = Query(min_length=3, max_length=200)) -> dict[str, Any]:
    """What is this variant and which sources confirm it. Evidence only, no verdict."""
    state = await build_runner(settings).clerk.build_state(variant.strip())
    v = state.variant
    cons = next((e for e in state.evidence_items if e.id == "ev_vep_consequence"), None)
    clinvar = [e for e in state.evidence_items if e.source == "ClinVar"]
    pop = next((e for e in state.evidence_items if e.evidence_type == "population_frequency"), None)
    words = {
        "frameshift_variant": "deletes or inserts letters and shifts the reading frame, so the protein is cut short",
        "stop_gained": "creates an early stop signal, so the protein is cut short",
        "missense_variant": "swaps one amino acid for another in the protein",
        "synonymous_variant": "changes a DNA letter without changing the protein",
        "splice_donor_variant": "breaks a splice site, so the gene is assembled wrongly",
        "splice_acceptor_variant": "breaks a splice site, so the gene is assembled wrongly",
        "intron_variant": "sits between coding segments and usually does not change the protein",
        "5_prime_UTR_variant": "sits in the untranslated region before the coding sequence",
    }
    c = (cons.metadata.get("consequence") if cons else None) or "unknown"
    return {
        "input": variant,
        "gene": v.gene,
        "transcript": v.transcript,
        "hgvs": v.hgvs,
        "rsid": v.rsid,
        "protein_change": cons.metadata.get("protein_change") if cons else None,
        "consequence": c,
        "what_it_does": words.get(c, c.replace("_", " ")),
        "disease_context": state.disease_context.disease_name if state.disease_context else None,
        "clinvar_classification": clinvar[0].metadata.get("classification") if clinvar else None,
        "clinvar_review": clinvar[0].metadata.get("review_status") if clinvar else None,
        "allele_frequency": pop.metadata.get("allele_frequency") if pop else None,
        "sources_confirmed": [s for s in state.sources_loaded if s != "cache"],
        "evidence": [e.model_dump(mode="json") for e in state.evidence_items],
        "disclaimer": DISCLAIMER,
    }


@app.get("/v1/stats")
async def stats() -> dict[str, Any]:
    runs = store.list_runs()
    events = store._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    agent_calls = store._conn.execute("SELECT COUNT(*) FROM events WHERE name IN ('pathogenic_agent','benign_agent','typesafe_cross_exam','jury')").fetchone()[0]
    lat = [r["latency_ms"] for r in runs]
    return {
        "cases": store._conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0],
        "completed": len(runs),
        "events": events,
        "agent_calls": agent_calls,
        "avg_latency_ms": round(sum(lat) / len(lat), 1) if lat else 0,
        "converged_rate": round(sum(1 for r in runs if r["converged"]) / len(runs), 3) if runs else 0,
        "recent_latency_ms": lat[-12:],
    }


@app.get("/v1/config")
async def config() -> dict[str, Any]:
    runner = build_runner(settings)
    return {
        **describe(runner),
        "llm_configured": settings.has_llm,
        "typesafe_configured": settings.has_typesafe,
        "weave_configured": settings.has_weave,
        "wandb_project": settings.wandb_project,
        "wandb_entity": settings.wandb_entity or None,
        "wandb_url": f"https://wandb.ai/{settings.wandb_entity}/{settings.wandb_project}" if settings.has_weave and settings.wandb_entity else None,
        "weave_url": f"https://wandb.ai/{settings.wandb_entity}/{settings.wandb_project}/weave" if settings.has_weave and settings.wandb_entity else None,
        "aria": optimizer.name,
        "demo_variants": DEMO_VARIANTS,
        "disclaimer": DISCLAIMER,
    }


@app.post("/v1/cases", status_code=201)
async def create_case(body: CreateCase) -> dict[str, Any]:
    case_id = f"case_{uuid.uuid4().hex[:8]}"
    cfg = {"max_rounds": body.max_rounds or settings.max_rounds, "typesafe_enabled": body.typesafe_enabled, "mode": settings.mode}
    case = store.create_case(case_id, body.variant.strip(), cfg)
    if body.run:
        _start(case_id)
        case["status"] = "running"
    return case


@app.get("/v1/cases")
async def list_cases(limit: int = Query(50, ge=1, le=200)) -> list[dict[str, Any]]:
    return store.list_cases(limit)


@app.post("/v1/cases/{case_id}/run")
async def run_case(case_id: str) -> dict[str, Any]:
    case = _case_or_404(case_id)
    if case["status"] == "completed":
        raise HTTPException(409, "case already completed")
    _start(case_id)
    return {"case_id": case_id, "status": "running"}


@app.get("/v1/cases/{case_id}")
async def get_case(case_id: str) -> dict[str, Any]:
    return _case_or_404(case_id)


@app.get("/v1/cases/{case_id}/evidence")
async def get_evidence(case_id: str) -> dict[str, Any]:
    case = _case_or_404(case_id)
    if case.get("result"):
        state = case["result"]["state"]
        return {"variant": state["variant"], "evidence_items": state["evidence_items"], "sources_loaded": state["sources_loaded"]}
    for ev in store.list_events(case_id):
        if ev["name"] == "evidence_retrieved":
            st = ev["payload"]["state"]
            return {"variant": st["variant"], "evidence_items": st["evidence_items"], "sources_loaded": st["sources_loaded"]}
    raise HTTPException(409, f"case is {case['status']}")


@app.get("/v1/cases/{case_id}/rounds")
async def get_rounds(case_id: str) -> list[dict[str, Any]]:
    return _result_or_409(_case_or_404(case_id))["rounds"]


@app.get("/v1/cases/{case_id}/verdict")
async def get_verdict(case_id: str) -> dict[str, Any]:
    return {**_result_or_409(_case_or_404(case_id))["verdict"], "disclaimer_ui": DISCLAIMER}


@app.get("/v1/cases/{case_id}/events")
async def get_events(case_id: str, after: int = 0) -> list[dict[str, Any]]:
    _case_or_404(case_id)
    return store.list_events(case_id, after)


@app.get("/v1/cases/{case_id}/stream")
async def stream_case(case_id: str, after: int = 0):
    _case_or_404(case_id)
    queue: asyncio.Queue = asyncio.Queue()
    _subscribers[case_id].append(queue)

    async def gen():
        try:
            for ev in store.list_events(case_id, after):
                yield {"event": ev["name"], "id": str(ev["seq"]), "data": json.dumps(ev)}
                if ev["name"] in ("case_completed", "case_failed"):
                    return
            case = store.get_case(case_id)
            if case and case["status"] in ("completed", "failed"):
                return
            while True:
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
                    continue
                yield {"event": ev["name"], "id": str(ev["seq"]), "data": json.dumps(ev, default=str)}
                if ev["name"] in ("case_completed", "case_failed"):
                    return
        finally:
            _subscribers[case_id].remove(queue)

    return EventSourceResponse(gen())


@app.get("/v1/research/analysis")
async def research_analysis() -> dict[str, Any]:
    runs = [RunRecord.model_validate(r) for r in store.list_runs()]
    rec = await optimizer.analyze(runs)
    return {"recommendation": rec.model_dump(), "runs": [r.model_dump() for r in runs][-50:], "optimizer": optimizer.name}


@app.post("/v1/research/experiment", status_code=201)
async def research_experiment(body: ExperimentRequest) -> dict[str, Any]:
    if body.max_rounds is None:
        runs = [RunRecord.model_validate(r) for r in store.list_runs()]
        rec = await optimizer.analyze(runs)
        max_rounds = int(rec.recommended_config.get("max_rounds", settings.max_rounds))
    else:
        max_rounds = body.max_rounds
    ids = []
    for v in body.variants or DEMO_VARIANTS:
        cid = f"case_{uuid.uuid4().hex[:8]}"
        store.create_case(cid, v, {"max_rounds": max_rounds, "typesafe_enabled": body.typesafe_enabled, "mode": settings.mode, "experiment": True})
        _start(cid)
        ids.append(cid)
    return {"case_ids": ids, "max_rounds": max_rounds, "typesafe_enabled": body.typesafe_enabled}


# Single-container deploy: serve the generated Nuxt app (apps/web/.output/public) if it was built.
_web = ROOT / "apps" / "web" / ".output" / "public"
if _web.is_dir():
    app.mount("/", StaticFiles(directory=_web, html=True), name="web")
