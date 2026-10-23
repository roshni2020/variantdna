# VariantCourt

An AI courtroom for DNA variant interpretation, built for **CoreWeave Hacks: Agent Loops**
(Weights & Biases, TypeSafe AI, AGI House).

One agent argues a variant may cause disease, another argues it may be benign, TypeSafe
cross-examines both, and a jury revises a shared structured state over up to three rounds.
A deterministic ACMG-style rule engine, not an LLM, issues the final classification. Weave
traces every step; ARIA (in W&B) compares runs and recommends better loop configurations.

**Research prototype only. Not for clinical diagnosis.**

## Run it

```
# backend (FastAPI, port 8000)
uv sync --extra dev --extra observability
uv run uvicorn services.api.main:app --port 8000

# frontend (Nuxt 4, port 3000)
cd apps/web && npm install && npm run dev

# CLI demo without the API
uv run python scripts/run_case.py "NM_007294.4:c.68_69delAG"

# seed runs across configurations so ARIA / the Research Optimizer have data
uv run python scripts/seed_runs.py

# tests
uv run pytest

# marimo research notebook (reads runs from the API)
uv sync --extra notebook
uv run marimo edit evals/variantcourt_research.py
```

### Docker (one container, API + UI on port 8000)

```
docker build -t variantcourt .
docker run -p 8000:8000 --env-file .env -v variantcourt-data:/data variantcourt
```

Open http://localhost:8000. Set `CORS_ORIGINS` and `MAX_CONCURRENT_CASES` for a public deploy
(see `.env.example`). Cases still running when the server restarts are marked failed on boot.

Open http://localhost:3000, enter `NM_007294.4:c.68_69delAG`, click **Open case**, and watch
the sides argue live. The **Research Optimizer** tab shows ARIA's recommendation and links to
the W&B project.

## Keys (.env)

| Variable | Purpose | Status |
| --- | --- | --- |
| `WANDB_API_KEY`, `WANDB_ENTITY`, `WANDB_PROJECT` | Weave traces + W&B runs for ARIA | set |
| `COREWEAVE_BASE_URL`, `COREWEAVE_API_KEY`, `COREWEAVE_MODEL` | LLM-backed counsel and jury. Default: W&B Inference (CoreWeave-hosted, `https://api.inference.wandb.ai/v1`), which reuses `WANDB_API_KEY` | set |
| `TYPESAFE_BASE_URL`, `TYPESAFE_API_KEY`, `TYPESAFE_MODEL` | real TypeSafe cross-examiner | needed |
| `FALLBACK_BASE_URL`, `FALLBACK_API_KEY`, `FALLBACK_MODEL` | optional open-model fallback | optional |
| `VARIANTCOURT_MODE` | `demo` (deterministic agents) or `live` (LLM agents, deterministic fallback) | live |

With no model keys the app runs fully in DEMO MODE with deterministic agents. Every live
agent falls back to its deterministic twin if its endpoint fails, so the demo never dies.

## Layout

```
packages/variantcourt/
  domain/        shared Pydantic schemas + state hashing
  agents/        one file per agent:
                   evidence_clerk.py, pathogenic_counsel.py, benign_counsel.py,
                   cross_examiner.py (TypeSafe), jury.py  (mock + LLM versions each)
  evidence/      variant normalization + demo fixtures
  providers/     ModelProvider, OpenAI-compatible adapter (CoreWeave), settings
  loopcore/      reducer, convergence, courtroom loop, tracers (memory / streaming / Weave), W&B run logger
  acmg/          simplified ACMG-style criteria + combination rules
  research/      local run analysis (ARIA itself runs inside W&B)
  factory.py     builds a runner from settings (mock vs live)
services/api/    FastAPI: cases, SSE stream, research endpoints, SQLite store
apps/web/        Nuxt 4 courtroom UI + Research Optimizer
scripts/         run_case.py, seed_runs.py
tests/
```

## How the loop works

```
Evidence Clerk -> Pathogenic Counsel -> Benign Counsel -> TypeSafe Cross-Examiner -> Jury
      -> deterministic reducer -> convergence check -> repeat (max 3) -> ACMG rule engine
```

- Agents cite only existing evidence IDs; the reducer drops anything else.
- Counsels answer each other directly within a round through structured rebuttals (`rebuts` = opposing claim id); no free-form chat is exchanged.
- A claim's identity is its side plus the evidence it cites, so a rejected argument cannot return under a new criterion label.
- Evidence is immutable after ingestion; only the reducer produces a new state.
- TypeSafe runs every round and the jury may not act until it returns. Its rejections bind the jury.
- Convergence requires a round with no rejections, no new medium/high conflict and unchanged criterion claims; the loop never stops because a model says "final".
- If the round cap is hit with an unresolved high-severity conflict, the verdict is `NEEDS_REVIEW`.

## Demo cases

| Input | Expected |
| --- | --- |
| `NM_007294.4:c.68_69delAG` | Pathogenic; overreaching claims rejected in round 1, converged round 2 |
| `NM_007294.4:c.4837A>G` | Benign (BA1) |
| `BRAF V600E` | VUS, review flagged; ClinVar germline records conflict |
| anything else | Insufficient Evidence, flagged for human review |

Accepted input formats: transcript HGVS (`NM_007294.4:c.68_69delAG`), ClinVar style with the gene in parentheses (`NM_004333.6(BRAF):c.1799T>A`), dbSNP ids (`rs80357914`), and clinician shorthand at the protein level (`BRAF V600E`, `CFTR F508del`, `TP53 p.Arg248Trp`), which is resolved to transcript HGVS through ClinVar.

Evidence comes live from Ensembl VEP, gnomAD, ClinVar and Europe PMC (`EVIDENCE_MODE=live`, cached under `.cache/evidence/`, fixture fallback if the anchor source fails). Set `EVIDENCE_MODE=fixtures` for the offline demo bundle.

Rule engine covers PVS1, PS1, PS3, PM2, BA1, BS1, BS3, BP4, plus PP5/BP6 for 2+ star ClinVar classifications (a labeled research shortcut).

## Sponsor integrations

- **Weave**: every agent call, cross-examination, jury delta, round metric and verdict is an op under one trace per case.
- **ARIA**: each case is a W&B run (config: max_rounds, typesafe_enabled, provider; metrics per round). Open the project, click *Ask ARIA*. The Research Optimizer tab runs the same comparison locally and can launch the recommended experiment.
- **TypeSafe AI**: `agents/cross_examiner.py` holds the interface, a deterministic implementation of the checks, and an API adapter that merges real TypeSafe findings with them.
- **CoreWeave**: `providers/openai_compat.py` targets CoreWeave's OpenAI-compatible inference gateway with fallback.
- **marimo**: `evals/variantcourt_research.py` is a reactive notebook that plots whether rejections and conflicts fall across rounds, latency vs open conflicts per configuration, and one case's round-by-round trajectory.
