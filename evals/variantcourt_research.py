# /// script
# dependencies = ["marimo", "pandas", "altair", "httpx"]
# ///
"""VariantCourt research notebook (marimo).

Answers the loop question: are the agents improving across rounds, or just looping?
Reads runs from the VariantCourt API (SQLite-backed) and, optionally, from W&B.

Run:  uv run marimo edit evals/variantcourt_research.py
"""

import marimo

__generated_with = "0.19.0"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    import pandas as pd
    import altair as alt
    import httpx

    mo.md(
        """
        # VariantCourt Research Notebook
        **Research prototype - not for clinical diagnosis.**

        The courtroom loop runs up to N rounds per variant. This notebook checks whether
        each round actually improves the case (fewer rejected claims, fewer open conflicts,
        stable criteria) and which `max_rounds` configuration is worth the latency.
        """
    )
    return alt, httpx, mo, pd


@app.cell
def _(mo):
    api_base = mo.ui.text(value="http://127.0.0.1:8000", label="VariantCourt API")
    api_base
    return (api_base,)


@app.cell
def _(api_base, httpx, mo, pd):
    def load_runs(base: str) -> pd.DataFrame:
        r = httpx.get(f"{base}/v1/research/analysis", timeout=30)
        r.raise_for_status()
        return pd.DataFrame(r.json()["runs"])

    SNAPSHOT_URL = "https://raw.githubusercontent.com/PLACEHOLDER/variantcourt/main/evals/runs_snapshot.json"
    try:
        runs = load_runs(api_base.value)
        status = mo.md(f"Loaded **{len(runs)}** runs live from the API.")
    except Exception:  # noqa: BLE001
        # ponytail: molab cannot reach localhost; fall back to the committed snapshot next to this file, then a URL.
        import json, pathlib
        snap = pathlib.Path(__file__).with_name("runs_snapshot.json") if "__file__" in globals() else pathlib.Path("runs_snapshot.json")
        try:
            data = json.loads(snap.read_text()) if snap.exists() else httpx.get(SNAPSHOT_URL, timeout=20).json()
            runs = pd.DataFrame(data["runs"])
            status = mo.md(f"API unreachable; loaded **{len(runs)}** runs from the snapshot `{snap.name}`.")
        except Exception as e:  # noqa: BLE001
            runs = pd.DataFrame()
            status = mo.md(f"No API and no snapshot: `{e}`.")
    status
    return load_runs, runs


@app.cell
def _(mo, runs):
    mo.stop(runs.empty, mo.md("No runs yet. Run `uv run python scripts/seed_runs.py`."))
    summary = (
        runs.groupby(["max_rounds", "typesafe_enabled"])
        .agg(
            runs=("case_id", "count"),
            rounds_used=("rounds_used", "mean"),
            latency_ms=("latency_ms", "mean"),
            open_conflicts=("conflicts_unresolved", "mean"),
            open_high=("conflicts_unresolved_high", "mean"),
            converged=("converged", "mean"),
            needs_review=("requires_human_review", "mean"),
            rejected_r1=("rejected_claims_round1", "mean"),
            rejected_last=("rejected_claims_last", "mean"),
        )
        .round(3)
        .reset_index()
    )
    mo.vstack([mo.md("## By configuration"), mo.ui.table(summary)])
    return (summary,)


@app.cell
def _(alt, mo, runs):
    mo.stop(runs.empty)
    melted = runs.melt(
        id_vars=["case_id", "max_rounds", "typesafe_enabled"],
        value_vars=["rejected_claims_round1", "rejected_claims_last"],
        var_name="stage",
        value_name="rejected_claims",
    )
    melted["stage"] = melted["stage"].map({"rejected_claims_round1": "round 1", "rejected_claims_last": "last round"})
    chart = (
        alt.Chart(melted)
        .mark_bar()
        .encode(
            x=alt.X("stage:N", title=None, sort=["round 1", "last round"]),
            y=alt.Y("mean(rejected_claims):Q", title="rejected claims per run"),
            color=alt.Color("typesafe_enabled:N", title="TypeSafe"),
            column=alt.Column("max_rounds:O", title="max_rounds"),
        )
        .properties(height=220)
    )
    mo.vstack([
        mo.md("## Do rejections fall across rounds?\nIf the loop works, claims rejected in round 1 should not reappear in the last round."),
        mo.ui.altair_chart(chart),
    ])
    return


@app.cell
def _(alt, mo, runs):
    mo.stop(runs.empty)
    lat = (
        alt.Chart(runs)
        .mark_point(size=90, filled=True)
        .encode(
            x=alt.X("latency_ms:Q", title="latency (ms)"),
            y=alt.Y("conflicts_unresolved:Q", title="open conflicts at verdict"),
            color=alt.Color("max_rounds:O", title="max_rounds"),
            shape=alt.Shape("typesafe_enabled:N", title="TypeSafe"),
            tooltip=["case_id", "variant", "classification", "rounds_used", "converged"],
        )
        .properties(height=260)
    )
    mo.vstack([mo.md("## Latency vs open conflicts\nMore rounds should buy fewer open conflicts, or they are not worth it."), mo.ui.altair_chart(lat)])
    return


@app.cell
def _(api_base, httpx, mo, runs):
    mo.stop(runs.empty)
    try:
        import json, pathlib
        try:
            rec = httpx.get(f"{api_base.value}/v1/research/analysis", timeout=30).json()["recommendation"]
        except Exception:  # noqa: BLE001
            rec = json.loads(pathlib.Path(__file__).with_name("runs_snapshot.json").read_text())["recommendation"]
        text = f"""## Research Optimizer (ARIA-style) recommendation
        **Runs analyzed:** {rec['runs_analyzed']}

        **Observed:** {rec['observed']}

        **Hypothesis:** {rec['hypothesis']}

        **Recommended experiment:** {rec['recommended_experiment']}

        **Expected:** {rec['expected_improvement']}
        """
    except Exception as e:  # noqa: BLE001
        text = f"Could not load recommendation: `{e}`"
    mo.md(text)
    return


@app.cell
def _(mo):
    mo.md(
        """
        ## Per-round trajectory of one case
        Pick a case to see the round-by-round metrics Weave records.
        """
    )
    return


@app.cell
def _(mo, runs):
    mo.stop(runs.empty)
    case_pick = mo.ui.dropdown(options=list(runs["case_id"]), value=runs["case_id"].iloc[-1], label="case")
    case_pick
    return (case_pick,)


@app.cell
def _(alt, api_base, case_pick, httpx, mo, pd):
    mo.stop(case_pick.value is None)
    try:
        events = httpx.get(f"{api_base.value}/v1/cases/{case_pick.value}/events", timeout=30).json()
    except Exception:  # noqa: BLE001
        events = []
        mo.stop(True, mo.md("Per-round trajectory needs the live API (not available on molab)."))
    rows = [
        {"round": e["payload"]["round"], **{k: v for k, v in e["payload"].items() if isinstance(v, (int, float)) and k != "round"}}
        for e in events
        if e["name"] == "round_metrics"
    ]
    traj = pd.DataFrame(rows)
    if traj.empty:
        out = mo.md("No round metrics for this case.")
    else:
        long = traj.melt(id_vars="round", value_vars=[c for c in ["number_of_conflicts", "number_of_rejected_claims", "state_change_score"] if c in traj], var_name="metric")
        ch = (
            alt.Chart(long)
            .mark_line(point=True)
            .encode(x=alt.X("round:O"), y=alt.Y("value:Q"), color="metric:N")
            .properties(height=240)
        )
        out = mo.vstack([mo.ui.table(traj), mo.ui.altair_chart(ch)])
    out
    return


if __name__ == "__main__":
    app.run()
