"""End-to-end EgoScope run: confirmed scope → EgoSelect → artifacts."""

from __future__ import annotations

import csv
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from analysis.brief import render_brief
from analysis.compare import (
    budget_delta,
    dataset_diagnosis,
    greedy_order,
    method_metrics,
    overlap,
    prefix_until_coverage,
    random_range,
    strategy_overlap,
)
from analysis.recommend import recommend
from egoselect import __version__
from egoselect.baselines import budget_count, keep_prefix, rankings
from egoselect.explain import explain_step
from egoselect.metrics import evaluate_keep
from requirements.compiler import (
    CompiledRun,
    compile_scope,
    file_fingerprint,
    scope_hash,
    weights_for_profile,
)
from requirements.feasibility import assess_scope
from requirements.parser import parse_request
from requirements.registry import load_profiles
from requirements.schema import RequestType, Scope, ScopeProposal

ROOT = Path(__file__).resolve().parents[1]
FEATURES_PATH = ROOT / "outputs" / "episode_features.parquet"
RUNS_DIR = ROOT / "outputs" / "runs"
RANDOM_SEEDS = [42, 43, 44, 45, 46]


def load_features(path: Path = FEATURES_PATH) -> pd.DataFrame:
    return pd.read_parquet(path)


def propose_scope(request: str) -> ScopeProposal:
    return parse_request(request)


def _dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".json":
        path.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    else:
        path.write_text(str(payload) if not isinstance(payload, str) else payload)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _selection_rows(frame: pd.DataFrame, k: int, features: pd.DataFrame) -> list[dict[str, Any]]:
    meta = features.set_index("episode_hash")
    ordered = frame.sort_values("selection_rank")
    rows = []
    for _, rec in ordered.iterrows():
        hid = str(rec["episode_hash"])
        info = meta.loc[hid]
        rows.append(
            {
                "episode_hash": hid,
                "selection_rank": int(rec["selection_rank"]),
                "kept": int(rec["selection_rank"]) <= k,
                "quality": float(rec.get("quality", info["quality_score"])),
                "coverage_gain": rec.get("coverage_gain"),
                "redundancy": rec.get("redundancy"),
                "value": rec.get("value"),
                "behavioral_region": int(info["behavioral_region"]),
                "stationary_ratio": float(info["stationary_ratio"]),
                "pca_x": float(info["pca_x"]),
                "pca_y": float(info["pca_y"]),
                "reason": rec.get("reason", ""),
            }
        )
    return rows


def _attach_reasons(frame: pd.DataFrame, result) -> pd.DataFrame:
    if result is None:
        if "reason" not in frame.columns:
            frame = frame.copy()
            frame["reason"] = ""
        return frame
    out = frame.copy()
    out["reason"] = [explain_step(rec) for rec in result.order]
    return out


def execute_compiled(
    scope: Scope,
    compiled: CompiledRun,
    features: pd.DataFrame,
) -> dict[str, Any]:
    defaults = load_profiles()["defaults"]
    seeds = list(defaults.get("random_seeds") or RANDOM_SEEDS)
    eligible = compiled.eligible
    method_rows: list[dict[str, Any]] = []
    selected_ids: list[str] = []
    ego_frame = None
    ego_result = None
    ranked = None
    k = compiled.k
    extra: dict[str, Any] = {}

    if scope.request_type == RequestType.diagnose_dataset:
        extra["diagnosis"] = dataset_diagnosis(features)
        primary = extra["diagnosis"]["full_pool"]
        rec = recommend(scope, [])
        return {
            "primary_metrics": primary,
            "method_rows": [],
            "selected_ids": features["episode_hash"].astype(str).tolist(),
            "selection_frame": None,
            "recommendation": rec,
            "extra": extra,
            "k": len(features),
        }

    if scope.request_type == RequestType.unsupported_or_unknown and not compiled.feasible:
        rec = recommend(scope, [])
        return {
            "primary_metrics": {},
            "method_rows": [],
            "selected_ids": [],
            "selection_frame": None,
            "recommendation": rec,
            "extra": extra,
            "k": 0,
        }

    if compiled.stop_on_full_coverage:
        ego_frame, ego_result = greedy_order(
            eligible, objective="egoselect", weights=compiled.weights
        )
        ego_frame = _attach_reasons(ego_frame, ego_result)
        ordered = ego_frame.sort_values("selection_rank")["episode_hash"].astype(str).tolist()
        k = prefix_until_coverage(eligible, ordered)
        selected_ids = ordered[:k]
        primary = evaluate_keep(eligible, selected_ids)
        method_rows.append({"method": "EgoSelect", **primary})
        extra["minimum_k"] = k
        extra["coverage_stop"] = True
        rec = recommend(scope, method_rows)
        return {
            "primary_metrics": primary,
            "method_rows": method_rows,
            "selected_ids": selected_ids,
            "selection_frame": ego_frame,
            "recommendation": rec,
            "extra": extra,
            "k": k,
        }

    if scope.request_type == RequestType.test_strategy:
        k = compiled.k or budget_count(compiled.n_universe, 0.30)
        profiles = {
            name: weights_for_profile(name) for name in compiled.strategy_profiles
        }
        extra["strategy"] = strategy_overlap(eligible, k, profiles)
        # Use balanced EgoSelect as the displayed subset.
        ego_frame, ego_result = greedy_order(
            eligible, objective="egoselect", weights=compiled.weights
        )
        ego_frame = _attach_reasons(ego_frame, ego_result)
        selected_ids = keep_prefix(ego_frame, k)
        primary = evaluate_keep(eligible, selected_ids)
        rec = {
            "method": "EgoSelect",
            "profile": compiled.profile,
            "reason": (
                f"{extra['strategy']['n_core']} episodes are selected by every "
                f"tested profile at k={k}."
            ),
            "confidence": "moderate",
            "tie": False,
            "rule": "selection overlap across weight profiles",
        }
        return {
            "primary_metrics": primary,
            "method_rows": [],
            "selected_ids": selected_ids,
            "selection_frame": ego_frame,
            "recommendation": rec,
            "extra": extra,
            "k": k,
        }

    if scope.request_type == RequestType.compare_budgets:
        ego_frame, ego_result = greedy_order(
            eligible, objective="egoselect", weights=compiled.weights
        )
        ego_frame = _attach_reasons(ego_frame, ego_result)
        ordered = ego_frame.sort_values("selection_rank")["episode_hash"].astype(str).tolist()
        low, high = compiled.compare_budgets[0], compiled.compare_budgets[-1]
        extra["budget_delta"] = budget_delta(eligible, ordered, low, high)
        k = extra["budget_delta"]["k_high"]
        selected_ids = ordered[:k]
        primary = extra["budget_delta"]["high"]
        method_rows.append({"method": "EgoSelect@high", **primary, "n_keep": k})
        method_rows.append(
            {
                "method": "EgoSelect@low",
                **extra["budget_delta"]["low"],
                "n_keep": extra["budget_delta"]["k_low"],
            }
        )
        rec = recommend(scope, [{"method": "EgoSelect", **primary}])
        rec["reason"] = (
            f"The larger budget adds {extra['budget_delta']['delta']['n_added']} "
            f"episodes; coverage delta "
            f"{extra['budget_delta']['delta']['coverage']:.3f}."
        )
        return {
            "primary_metrics": primary,
            "method_rows": method_rows,
            "selected_ids": selected_ids,
            "selection_frame": ego_frame,
            "recommendation": rec,
            "extra": extra,
            "k": k,
        }

    k = compiled.k or budget_count(compiled.n_universe, 0.30)
    ranked = rankings(eligible, seed=compiled.seed, weights=compiled.weights)
    ego_frame, ego_result = ranked["EgoSelect"]
    ego_frame = _attach_reasons(ego_frame, ego_result)
    for name in compiled.methods:
        if name == "Random":
            row = random_range(eligible, k, seeds)
            row["method"] = "Random"
            row["n_keep"] = k
            method_rows.append(row)
            continue
        frame, _result = ranked[name]
        metrics = method_metrics(eligible, frame, k)
        metrics["method"] = name
        method_rows.append(metrics)

    selected_ids = keep_prefix(ego_frame, k)
    primary = evaluate_keep(eligible, selected_ids)
    extra["overlaps"] = {}
    ego_ids = selected_ids
    for row in method_rows:
        if row["method"] == "EgoSelect" or "episode_ids" not in row:
            continue
        extra["overlaps"][row["method"]] = overlap(ego_ids, row["episode_ids"])

    rec = recommend(scope, method_rows)
    return {
        "primary_metrics": primary,
        "method_rows": method_rows,
        "selected_ids": selected_ids,
        "selection_frame": ego_frame,
        "recommendation": rec,
        "extra": extra,
        "k": k,
        "ranked": ranked,
    }


def _tradeoff(result: dict[str, Any]) -> str:
    rows = {row["method"]: row for row in result["method_rows"]}
    if "Dedup-only" in rows and "EgoSelect" in rows:
        ded = rows["Dedup-only"]["nn_redundancy"]
        ego = rows["EgoSelect"]["nn_redundancy"]
        if isinstance(ded, dict) or isinstance(ego, dict):
            return "See measured method table."
        if ded < ego:
            return (
                "Dedup-only produces lower redundancy, while EgoSelect better "
                "serves a coverage- or quality-weighted objective."
            )
    if result.get("extra", {}).get("budget_delta"):
        d = result["extra"]["budget_delta"]["delta"]
        return (
            f"Increasing the budget adds {d['n_added']} episodes with coverage "
            f"delta {d['coverage']:.3f} and redundancy delta {d['redundancy']:.3f}."
        )
    if result.get("extra", {}).get("strategy"):
        n_core = result["extra"]["strategy"]["n_core"]
        return (
            f"{n_core} episodes are selected under every tested weight profile."
        )
    return "See measured method table."


def run_confirmed(
    scope: Scope,
    *,
    features: pd.DataFrame | None = None,
    proposed: ScopeProposal | None = None,
    feature_source: str = "bundled_demo",
) -> dict[str, Any]:
    features = features if features is not None else load_features()
    fingerprint = file_fingerprint(FEATURES_PATH)
    if proposed is None:
        proposed = assess_scope(scope, [])
        proposed.proposed_scope = scope
    compiled = compile_scope(scope, features, feature_fingerprint=fingerprint)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "original_request.txt").write_text(scope.original_request.strip() + "\n")
    _dump(run_dir / "proposed_scope.json", proposed.model_dump(mode="json"))
    _dump(run_dir / "confirmed_scope.json", scope.model_dump(mode="json"))

    feasibility = {
        "feasible": compiled.feasible,
        "reason": compiled.infeasible_reason,
        "n_universe": compiled.n_universe,
        "n_eligible": compiled.n_eligible,
        "requested_k": compiled.k,
        "constraint_steps": compiled.constraint_steps,
    }
    _dump(run_dir / "feasibility.json", feasibility)

    run_config = {
        "run_id": run_id,
        "code_version": __version__,
        "feature_source": feature_source,
        "feature_fingerprint": fingerprint,
        "scope_hash": compiled.scope_hash,
        "profile": compiled.profile,
        "weights": {
            "alpha": compiled.weights.alpha,
            "beta": compiled.weights.beta,
            "gamma": compiled.weights.gamma,
        },
        "seed": compiled.seed,
        "k": compiled.k,
        "methods": compiled.methods,
        "n_regions": compiled.n_regions,
        "stop_on_full_coverage": compiled.stop_on_full_coverage,
    }
    _dump(run_dir / "run_config.json", run_config)

    skip_rank = (not compiled.feasible) or (
        scope.request_type == RequestType.unsupported_or_unknown
        and not proposed.can_execute
    )
    if skip_rank:
        executed = {
            "primary_metrics": {},
            "method_rows": [],
            "selected_ids": [],
            "selection_frame": None,
            "recommendation": {
                "method": None,
                "profile": compiled.profile,
                "reason": compiled.infeasible_reason
                or "No executable analysis is supported for this request.",
                "confidence": "high",
                "tie": False,
            },
            "extra": {},
            "k": 0,
        }
        analysis = _analysis_payload(
            scope, proposed, compiled, executed, fingerprint, run_id
        )
        _dump(run_dir / "analysis.json", analysis)
        _write_csv(run_dir / "selected_manifest.csv", [])
        _write_csv(run_dir / "baseline_metrics.csv", [])
        brief = render_brief(analysis)
        (run_dir / "decision_brief.md").write_text(brief)
        return {
            "run_id": run_id,
            "dir": str(run_dir),
            "analysis": analysis,
            "brief": brief,
        }

    executed = execute_compiled(scope, compiled, features)
    analysis = _analysis_payload(scope, proposed, compiled, executed, fingerprint, run_id)
    _dump(run_dir / "analysis.json", analysis)

    k = executed["k"]
    frame = executed["selection_frame"]
    if frame is not None:
        _write_csv(run_dir / "selected_manifest.csv", _selection_rows(frame, k, compiled.eligible))
    else:
        _write_csv(run_dir / "selected_manifest.csv", [])

    baseline_rows = []
    for row in executed["method_rows"]:
        flat = {"method": row.get("method"), "n_keep": row.get("n_keep", executed["k"])}
        for key in (
            "behavioral_region_coverage",
            "average_quality",
            "nn_redundancy",
            "stationary_content_ratio",
            "visual_coverage",
            "motion_coverage",
        ):
            val = row.get(key)
            if isinstance(val, dict):
                flat[key] = val.get("mean")
                flat[f"{key}_min"] = val.get("min")
                flat[f"{key}_max"] = val.get("max")
            else:
                flat[key] = val
        baseline_rows.append(flat)
    _write_csv(run_dir / "baseline_metrics.csv", baseline_rows)

    brief = render_brief(analysis)
    (run_dir / "decision_brief.md").write_text(brief)
    return {"run_id": run_id, "dir": str(run_dir), "analysis": analysis, "brief": brief}


def _analysis_payload(
    scope: Scope,
    proposed: ScopeProposal,
    compiled: CompiledRun,
    executed: dict[str, Any],
    fingerprint: str,
    run_id: str,
) -> dict[str, Any]:
    proxies = [
        r.limitation
        for r in proposed.requirements
        if r.status.value == "proxy" and r.limitation
    ]
    unsupported = [
        f"{r.text}: {r.limitation or r.unsupported_concept}"
        for r in proposed.requirements
        if r.status.value in {"unsupported", "prohibited"}
    ]
    return {
        "run_id": run_id,
        "confirmed_scope": scope.model_dump(mode="json"),
        "scope_hash": compiled.scope_hash,
        "feasibility": {
            "feasible": compiled.feasible,
            "reason": compiled.infeasible_reason,
            "n_universe": compiled.n_universe,
            "n_eligible": compiled.n_eligible,
            "requested_k": compiled.k,
            "constraint_steps": compiled.constraint_steps,
        },
        "recommendation": executed["recommendation"],
        "primary_metrics": executed["primary_metrics"],
        "method_rows": [
            {k: v for k, v in row.items() if k != "episode_ids"}
            for row in executed["method_rows"]
        ],
        "selected_ids": executed["selected_ids"],
        "k": executed["k"],
        "unsupported": unsupported,
        "proxies": proxies,
        "tradeoff": _tradeoff(executed),
        "extra": {
            key: value
            for key, value in executed.get("extra", {}).items()
            if key != "strategy" or True
        },
        "next_validation_step": (
            "Validate the selected subset with a held-out downstream evaluation; "
            "this brief does not measure policy success."
        ),
        "provenance": {
            **compiled.provenance,
            "code_version": __version__,
            "feature_fingerprint": fingerprint,
            "run_id": run_id,
        },
        "canvas_episodes": _canvas_episodes(executed, compiled),
    }


def _canvas_episodes(executed: dict[str, Any], compiled: CompiledRun) -> list[dict[str, Any]]:
    frame = executed.get("selection_frame")
    if frame is None:
        return []
    k = executed["k"]
    meta = compiled.eligible.set_index("episode_hash")
    rows = []
    for _, rec in frame.sort_values("selection_rank").iterrows():
        hid = str(rec["episode_hash"])
        info = meta.loc[hid]
        rows.append(
            {
                "id": hid,
                "x": float(info["pca_x"]),
                "y": float(info["pca_y"]),
                "region": int(info["behavioral_region"]),
                "rank": int(rec["selection_rank"]),
                "quality": float(rec.get("quality", info["quality_score"])),
                "coverage_gain": None if pd.isna(rec.get("coverage_gain")) else float(rec.get("coverage_gain")),
                "redundancy": None if pd.isna(rec.get("redundancy")) else float(rec.get("redundancy")),
                "value": None if pd.isna(rec.get("value")) else float(rec.get("value")),
                "nearest": "" if pd.isna(rec.get("nearest_selected_episode")) else str(rec.get("nearest_selected_episode") or ""),
                "stationary": float(info["stationary_ratio"]),
                "reason": str(rec.get("reason") or ""),
                "kept": int(rec["selection_rank"]) <= k,
            }
        )
    return rows


def load_run(run_id: str) -> dict[str, Any]:
    run_dir = RUNS_DIR / run_id
    analysis = json.loads((run_dir / "analysis.json").read_text())
    brief = (run_dir / "decision_brief.md").read_text()
    return {"run_id": run_id, "dir": str(run_dir), "analysis": analysis, "brief": brief}
