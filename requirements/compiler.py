"""Deterministic translation from a confirmed scope to EgoSelect parameters."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd

from egoselect.baselines import budget_count
from egoselect.scoring import Weights
from requirements.registry import (
    EXECUTABLE_FIELDS,
    is_registered_field,
    load_profiles,
    normalize_operator,
)
from requirements.schema import HardConstraint, PriorityLevel, RequestType, Scope, SourceKind

OPS: dict[str, Callable[[pd.Series, float], pd.Series]] = {
    "less_than_or_equal": lambda s, v: s <= v,
    "less_than": lambda s, v: s < v,
    "greater_than_or_equal": lambda s, v: s >= v,
    "greater_than": lambda s, v: s > v,
}

LEVEL_SCORE = {
    PriorityLevel.low: 0,
    PriorityLevel.medium: 1,
    PriorityLevel.high: 2,
}

METHOD_KEYS = {
    "random": "Random",
    "dedup_only": "Dedup-only",
    "diversity_only": "Diversity-only",
    "egoselect": "EgoSelect",
}


def scope_hash(scope: Scope | dict[str, Any]) -> str:
    payload = scope.model_dump(mode="json") if isinstance(scope, Scope) else scope
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def file_fingerprint(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def choose_profile(scope: Scope) -> str:
    if scope.strategy_profiles:
        return scope.strategy_profiles[0]
    scores = {
        "quality_first": LEVEL_SCORE[scope.soft_priorities.quality],
        "coverage_first": LEVEL_SCORE[scope.soft_priorities.coverage],
        "dedup_first": LEVEL_SCORE[scope.soft_priorities.redundancy_reduction],
    }
    best = max(scores.values())
    winners = [k for k, v in scores.items() if v == best]
    if best <= LEVEL_SCORE[PriorityLevel.medium] and len(winners) > 1:
        return "balanced"
    if len(winners) != 1:
        return "balanced"
    return winners[0]


def weights_for_profile(profile: str, custom: dict[str, float] | None = None) -> Weights:
    profiles = load_profiles()["profiles"]
    if custom:
        alpha = float(custom["quality"])
        beta = float(custom["coverage"])
        gamma = float(custom["redundancy_penalty"])
        total = alpha + beta + gamma
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"Custom weights must sum to 1.0, got {total}")
        return Weights(alpha=alpha, beta=beta, gamma=gamma)
    row = profiles[profile]
    return Weights(
        alpha=float(row["quality"]),
        beta=float(row["coverage"]),
        gamma=float(row["redundancy_penalty"]),
    )


def apply_hard_constraints(
    features: pd.DataFrame,
    constraints: list[HardConstraint],
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    pool = features.copy()
    steps: list[dict[str, Any]] = [
        {"constraint": "all", "n_remaining": int(len(pool)), "removed": 0}
    ]
    for constraint in constraints:
        if constraint.operator == "minimize":
            continue
        if constraint.field not in pool.columns:
            raise ValueError(f"Unknown constraint field {constraint.field}")
        if not is_registered_field(constraint.field):
            raise ValueError(f"Unregistered field {constraint.field}")
        if constraint.field not in EXECUTABLE_FIELDS:
            raise ValueError(f"Field {constraint.field} cannot be used as a hard filter")
        op = normalize_operator(constraint.operator)
        before = len(pool)
        mask = OPS[op](pool[constraint.field], constraint.value)
        pool = pool.loc[mask].copy()
        steps.append(
            {
                "constraint": constraint.requirement_id,
                "field": constraint.field,
                "operator": op,
                "value": constraint.value,
                "n_remaining": int(len(pool)),
                "removed": int(before - len(pool)),
            }
        )
    return pool.reset_index(drop=True), steps


def resolve_k(scope: Scope, n_universe: int, n_eligible: int) -> int | None:
    if scope.request_type in {RequestType.find_minimum_subset, RequestType.diagnose_dataset}:
        return None
    if scope.budget.value is None or scope.budget.unit is None:
        return None
    if scope.budget.unit == "episodes":
        return int(scope.budget.value)
    return budget_count(n_universe, float(scope.budget.value))


@dataclass
class CompiledRun:
    scope_hash: str
    profile: str
    weights: Weights
    eligible: pd.DataFrame
    constraint_steps: list[dict[str, Any]]
    k: int | None
    n_universe: int
    n_eligible: int
    feasible: bool
    infeasible_reason: str | None
    methods: list[str]
    compare_budgets: list[float]
    strategy_profiles: list[str]
    seed: int
    n_regions: int
    stop_on_full_coverage: bool
    provenance: dict[str, Any] = field(default_factory=dict)


def compile_scope(
    scope: Scope,
    features: pd.DataFrame,
    *,
    feature_fingerprint: str,
) -> CompiledRun:
    for constraint in scope.hard_constraints:
        if constraint.source == SourceKind.assumed and constraint.field == "stationary_ratio":
            # Assumed thresholds are allowed only after the user confirms the scope.
            pass
        normalize_operator(constraint.operator)
        if not is_registered_field(constraint.field):
            raise ValueError(f"Unregistered field {constraint.field} cannot enter the run config")

    eligible, steps = apply_hard_constraints(features, scope.hard_constraints)
    profile = choose_profile(scope)
    weights = weights_for_profile(profile)
    n_universe = int(len(features))
    n_eligible = int(len(eligible))
    k = resolve_k(scope, n_universe, n_eligible)
    feasible = True
    reason = None
    if k is not None and n_eligible < k:
        feasible = False
        reason = (
            f"Hard constraints leave {n_eligible} eligible episodes, "
            f"below requested keep size {k}."
        )
    if n_eligible == 0 and scope.request_type not in {
        RequestType.unsupported_or_unknown,
        RequestType.diagnose_dataset,
    }:
        feasible = False
        reason = "Hard constraints leave zero eligible episodes."

    methods = ["EgoSelect"]
    for key in scope.comparisons:
        name = METHOD_KEYS.get(key)
        if name and name not in methods:
            methods.append(name)
    if scope.request_type == RequestType.compare_methods and "Dedup-only" not in methods:
        methods.append("Dedup-only")

    compare_budgets: list[float] = []
    if scope.request_type == RequestType.compare_budgets:
        if scope.budget.compare_with is not None:
            compare_budgets = sorted(
                {float(scope.budget.compare_with), float(scope.budget.value or 0.3)}
            )
        elif scope.budget.value is not None:
            compare_budgets = [float(scope.budget.value)]

    strategy_profiles = list(scope.strategy_profiles)
    if scope.request_type == RequestType.test_strategy and not strategy_profiles:
        strategy_profiles = ["balanced", "quality_first", "coverage_first"]

    return CompiledRun(
        scope_hash=scope_hash(scope),
        profile=profile,
        weights=weights,
        eligible=eligible,
        constraint_steps=steps,
        k=k,
        n_universe=n_universe,
        n_eligible=n_eligible,
        feasible=feasible,
        infeasible_reason=reason,
        methods=methods,
        compare_budgets=compare_budgets,
        strategy_profiles=strategy_profiles,
        seed=int(scope.run_options.random_seed),
        n_regions=int(scope.run_options.number_of_regions),
        stop_on_full_coverage=scope.request_type == RequestType.find_minimum_subset,
        provenance={
            "feature_fingerprint": feature_fingerprint,
            "scope_hash": scope_hash(scope),
            "profile": profile,
            "weights": {
                "alpha": weights.alpha,
                "beta": weights.beta,
                "gamma": weights.gamma,
            },
            "seed": int(scope.run_options.random_seed),
        },
    )
