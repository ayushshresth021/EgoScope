"""Local FastAPI service for EgoScope scoping and runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from egoscope.pipeline import RUNS_DIR, load_run, propose_scope, run_confirmed
from requirements.feasibility import assess_scope
from requirements.schema import Scope

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_PATH = ROOT / "configs" / "example_requests.yaml"

app = FastAPI(title="EgoScope", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ScopeIn(BaseModel):
    request: str


class RunIn(BaseModel):
    confirmed_scope: dict[str, Any]
    feature_source: str = "bundled_demo"


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/examples")
def examples() -> dict[str, Any]:
    payload = yaml.safe_load(EXAMPLES_PATH.read_text())
    return payload


@app.post("/api/scope")
def scope_request(body: ScopeIn) -> dict[str, Any]:
    text = body.request.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty requests cannot be submitted.")
    proposal = propose_scope(text)
    return proposal.model_dump(mode="json")


@app.post("/api/runs")
def create_run(body: RunIn) -> dict[str, Any]:
    try:
        scope = Scope.model_validate(body.confirmed_scope)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid scope: {exc}") from exc
    parsed = propose_scope(scope.original_request)
    proposal = assess_scope(scope, parsed.requirements)
    result = run_confirmed(
        scope, proposed=proposal, feature_source=body.feature_source
    )
    analysis = result["analysis"]
    return {
        "run_id": result["run_id"],
        "status": "complete",
        "recommendation": analysis["recommendation"],
        "metrics": analysis["primary_metrics"],
        "artifact_dir": result["dir"],
        "errors": analysis["feasibility"].get("reason"),
        "can_execute": analysis["feasibility"]["feasible"],
    }


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    path = RUNS_DIR / run_id / "analysis.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Run not found")
    result = load_run(run_id)
    return {
        "run_id": run_id,
        "status": "complete",
        "analysis": result["analysis"],
        "brief": result["brief"],
        "artifact_dir": result["dir"],
        "errors": result["analysis"]["feasibility"].get("reason"),
    }


@app.get("/api/runs/{run_id}/brief")
def get_brief(run_id: str) -> dict[str, str]:
    path = RUNS_DIR / run_id / "decision_brief.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Run not found")
    return {"run_id": run_id, "markdown": path.read_text()}
