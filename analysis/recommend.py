"""Deterministic recommendation rules. LLM may not change the winner."""

from __future__ import annotations

from typing import Any

from analysis.compare import as_float
from requirements.compiler import choose_profile
from requirements.registry import load_profiles
from requirements.schema import RequestType, Scope


def _leaders(rows: list[dict[str, Any]], key: str, better: str) -> list[str]:
    vals = [(row["method"], as_float(row[key])) for row in rows]
    if better == "max":
        best = max(v for _, v in vals)
    else:
        best = min(v for _, v in vals)
    return [name for name, v in vals if abs(v - best) < 1e-12]


def recommend(
    scope: Scope,
    method_rows: list[dict[str, Any]],
    *,
    tolerance: float | None = None,
) -> dict[str, Any]:
    profiles = load_profiles()
    tol = float(tolerance if tolerance is not None else profiles["defaults"]["tie_tolerance"])
    profile = choose_profile(scope)
    if not method_rows:
        return {
            "method": None,
            "profile": profile,
            "reason": "No methods were evaluated.",
            "confidence": "low",
            "tie": False,
        }

    if scope.request_type == RequestType.diagnose_dataset:
        return {
            "method": None,
            "profile": profile,
            "reason": "Diagnosis does not select a subset.",
            "confidence": "moderate",
            "tie": False,
        }

    by_name = {row["method"]: row for row in method_rows}

    def metric(name: str, key: str) -> float:
        return as_float(by_name[name][key])

    names = [row["method"] for row in method_rows]
    if profile == "coverage_first" or (
        scope.request_type == RequestType.compare_methods
        and scope.soft_priorities.coverage.value == "high"
    ):
        ordered = sorted(
            names,
            key=lambda n: (
                -metric(n, "behavioral_region_coverage"),
                -metric(n, "average_quality"),
            ),
        )
        rule = "max coverage, then quality"
    elif profile == "dedup_first":
        ordered = sorted(
            names,
            key=lambda n: (
                metric(n, "nn_redundancy"),
                -metric(n, "average_quality"),
            ),
        )
        rule = "min redundancy, then quality"
    else:
        # Normalized weighted score using the confirmed profile weights.
        cov = [metric(n, "behavioral_region_coverage") for n in names]
        qual = [metric(n, "average_quality") for n in names]
        red = [metric(n, "nn_redundancy") for n in names]

        def norm(vals: list[float], invert: bool = False) -> dict[str, float]:
            lo, hi = min(vals), max(vals)
            scale = hi - lo
            out = {}
            for n, v in zip(names, vals):
                x = 0.5 if scale < 1e-12 else (v - lo) / scale
                out[n] = 1.0 - x if invert else x
            return out

        nc, nq, nr = norm(cov), norm(qual), norm(red, invert=True)
        w = profiles["profiles"][profile]
        scores = {
            n: w["quality"] * nq[n]
            + w["coverage"] * nc[n]
            + w["redundancy_penalty"] * nr[n]
            for n in names
        }
        ordered = sorted(names, key=lambda n: -scores[n])
        rule = f"normalized weighted metric ({profile})"

    winner = ordered[0]
    runner = ordered[1] if len(ordered) > 1 else None
    tie = False
    if runner:
        key = (
            "behavioral_region_coverage"
            if "coverage" in rule
            else "nn_redundancy"
            if "redundancy" in rule
            else "average_quality"
        )
        if "weighted" in rule:
            # already ordered by composite; treat close coverage+quality as tie
            d_cov = abs(
                metric(winner, "behavioral_region_coverage")
                - metric(runner, "behavioral_region_coverage")
            )
            d_red = abs(metric(winner, "nn_redundancy") - metric(runner, "nn_redundancy"))
            tie = d_cov < tol and d_red < tol
        else:
            d = abs(metric(winner, key) - metric(runner, key))
            tie = d < tol

    if tie:
        reason = (
            f"Evidence does not distinguish {winner} and {runner} under {rule} "
            f"(tolerance {tol})."
        )
        method = winner
        confidence = "low"
    else:
        reason = f"Recommend {winner} under confirmed {profile} objective ({rule})."
        method = winner
        confidence = "moderate"

    if scope.request_type == RequestType.unsupported_or_unknown:
        return {
            "method": None,
            "profile": profile,
            "reason": "Unsupported request; no selection recommendation.",
            "confidence": "high",
            "tie": False,
        }

    return {
        "method": method,
        "profile": profile,
        "reason": reason,
        "confidence": confidence,
        "tie": tie,
        "rule": rule,
    }
