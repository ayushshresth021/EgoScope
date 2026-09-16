"""Measured comparisons only. No LLM arithmetic."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from egoselect.baselines import budget_count, keep_prefix, random_ranking
from egoselect.metrics import evaluate_keep
from egoselect.scoring import Weights
from egoselect.selector import greedy_select, result_to_frame


def prefix_until_coverage(features: pd.DataFrame, ordered: list[str]) -> int:
    universe = set(features["behavioral_region"].astype(int))
    seen: set[int] = set()
    lookup = features.set_index("episode_hash")["behavioral_region"]
    for i, hid in enumerate(ordered, start=1):
        seen.add(int(lookup.loc[hid]))
        if seen >= universe:
            return i
    return len(ordered)


def method_metrics(
    features: pd.DataFrame,
    ranking: pd.DataFrame,
    k: int,
) -> dict[str, Any]:
    kept = keep_prefix(ranking, k)
    ev = evaluate_keep(features, kept)
    ev["episode_ids"] = kept
    return ev


def random_range(
    features: pd.DataFrame,
    k: int,
    seeds: list[int],
) -> dict[str, Any]:
    rows = []
    for seed in seeds:
        ranking = random_ranking(features, seed=seed)
        rows.append(evaluate_keep(features, keep_prefix(ranking, k)))
    frame = pd.DataFrame(rows)
    out: dict[str, Any] = {"n_seeds": len(seeds)}
    for col in (
        "behavioral_region_coverage",
        "average_quality",
        "nn_redundancy",
        "stationary_content_ratio",
    ):
        series = frame[col].astype(float)
        out[col] = {
            "mean": float(series.mean()),
            "min": float(series.min()),
            "max": float(series.max()),
        }
    return out


def overlap(a: list[str], b: list[str]) -> dict[str, Any]:
    sa, sb = set(a), set(b)
    inter = sa & sb
    return {
        "n_a": len(sa),
        "n_b": len(sb),
        "n_overlap": len(inter),
        "jaccard": float(len(inter) / max(len(sa | sb), 1)),
    }


def greedy_order(features: pd.DataFrame, *, objective: str, weights: Weights | None = None):
    result = greedy_select(features, weights=weights, objective=objective)
    frame = result_to_frame(result)
    return frame, result


def budget_delta(
    features: pd.DataFrame,
    ordered: list[str],
    low: float,
    high: float,
) -> dict[str, Any]:
    n = len(features)
    k_low = budget_count(n, low)
    k_high = budget_count(n, high)
    a = evaluate_keep(features, ordered[:k_low])
    b = evaluate_keep(features, ordered[:k_high])
    added = ordered[k_low:k_high]
    return {
        "low_budget": low,
        "high_budget": high,
        "k_low": k_low,
        "k_high": k_high,
        "low": a,
        "high": b,
        "delta": {
            "coverage": b["behavioral_region_coverage"] - a["behavioral_region_coverage"],
            "quality": b["average_quality"] - a["average_quality"],
            "redundancy": b["nn_redundancy"] - a["nn_redundancy"],
            "n_added": len(added),
        },
        "added_episode_ids": added,
    }


def dataset_diagnosis(features: pd.DataFrame) -> dict[str, Any]:
    quality = features["quality_score"].astype(float)
    stationary = features["stationary_ratio"].astype(float)
    region_counts = features["behavioral_region"].value_counts().sort_index()
    full = evaluate_keep(features, features["episode_hash"].astype(str).tolist())
    return {
        "n_episodes": int(len(features)),
        "n_regions": int(features["behavioral_region"].nunique()),
        "region_counts": {int(k): int(v) for k, v in region_counts.items()},
        "quality": {
            "min": float(quality.min()),
            "median": float(quality.median()),
            "max": float(quality.max()),
            "spread": float(quality.max() - quality.min()),
        },
        "stationary": {
            "min": float(stationary.min()),
            "median": float(stationary.median()),
            "max": float(stationary.max()),
        },
        "full_pool": full,
        "limitations": [
            "Quality is weakly discriminative on this cohort.",
            "Coverage regions are unsupervised visual-motion clusters, not skills.",
            "No downstream policy evidence is available.",
        ],
    }


def strategy_overlap(
    features: pd.DataFrame,
    k: int,
    profiles: dict[str, Weights],
) -> dict[str, Any]:
    selected: dict[str, list[str]] = {}
    for name, weights in profiles.items():
        frame, _ = greedy_order(features, objective="egoselect", weights=weights)
        selected[name] = keep_prefix(frame, k)
    sets = {name: set(ids) for name, ids in selected.items()}
    names = list(sets)
    core = set.intersection(*sets.values()) if sets else set()
    pairwise = {}
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            pairwise[f"{a}∩{b}"] = overlap(selected[a], selected[b])
    return {
        "k": k,
        "selected": selected,
        "n_core": len(core),
        "core_episode_ids": sorted(core),
        "pairwise": pairwise,
    }


def as_float(value: Any) -> float:
    if isinstance(value, dict):
        return float(value.get("mean", np.nan))
    return float(value)
