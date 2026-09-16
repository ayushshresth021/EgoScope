"""Golden-file checks against published EgoSelect outputs."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from egoselect.baselines import budget_count, keep_prefix, rankings
from egoselect.metrics import evaluate_keep

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden"
FEATURES = ROOT / "outputs" / "episode_features.parquet"

SCORE_COLS = [
    "quality",
    "quality_norm",
    "coverage_gain",
    "redundancy",
    "value",
    "nearest_similarity",
    "new_region",
    "distance_bonus",
    "region_balance",
    "stationary_ratio",
]


@pytest.fixture(scope="module")
def features() -> pd.DataFrame:
    return pd.read_parquet(FEATURES)


@pytest.fixture(scope="module")
def ego_result(features: pd.DataFrame):
    ranked = rankings(features, seed=42)
    return ranked


def test_rescore_passes_and_first_pick(ego_result) -> None:
    audit = json.loads((GOLDEN / "greedy_audit.json").read_text())
    frame, result = ego_result["EgoSelect"]
    assert result.n_rescore_passes == 80
    assert result.greedy_recomputed
    assert result.first_pick_hash == audit["first_pick"]
    assert result.second_pick_hash == audit["second_pick"]
    assert result.max_quality_hash == audit["max_quality"]
    assert abs(result.max_abs_value_shift_after_first - audit["max_abs_value_shift_after_first"]) < 1e-9
    assert frame.iloc[0]["episode_hash"] == audit["keep_example"]["episode"]
    assert frame.iloc[-1]["episode_hash"] == audit["drop_example"]["episode"]
    assert frame.iloc[0]["reason"] == audit["keep_example"]["reason"]
    assert frame.iloc[-1]["reason"] == audit["drop_example"]["reason"]


def test_selections_parity(ego_result) -> None:
    golden = pd.read_csv(GOLDEN / "selections.csv")
    frame, _ = ego_result["EgoSelect"]
    merged = frame.merge(
        golden,
        on="episode_hash",
        suffixes=("", "_g"),
    )
    assert list(frame.sort_values("selection_rank")["episode_hash"]) == list(
        golden.sort_values("selection_rank")["episode_hash"]
    )
    for col in SCORE_COLS:
        delta = (merged[col] - merged[f"{col}_g"]).abs().max()
        assert delta < 1e-6, f"{col} max abs delta {delta}"


def test_primary_budget_table(features: pd.DataFrame, ego_result) -> None:
    golden = pd.read_csv(GOLDEN / "experiment_results.csv")
    k = budget_count(len(features), 0.30)
    rows = []
    for name in ("EgoSelect", "Dedup-only", "Diversity-only", "Random"):
        ranking, _ = ego_result[name]
        kept = keep_prefix(ranking, k)
        ev = evaluate_keep(features, kept)
        gold = golden[
            (golden["method"] == name)
            & (golden["budget"] == 0.30)
            & (golden["corruption_rate"] == 0.0)
        ].iloc[0]
        assert abs(ev["behavioral_region_coverage"] - gold["behavioral_region_coverage"]) < 1e-9
        assert abs(ev["average_quality"] - gold["average_quality"]) < 1e-9
        assert abs(ev["nn_redundancy"] - gold["nn_redundancy"]) < 1e-9
        rows.append(ev)
    ego = rows[0]
    assert ego["behavioral_region_coverage"] == pytest.approx(1.0)
    assert ego["average_quality"] == pytest.approx(0.999, abs=5e-4)


def test_experiment_csv_parity() -> None:
    golden = pd.read_csv(GOLDEN / "experiment_results.csv")
    live = pd.read_csv(ROOT / "outputs" / "experiment_results.csv")
    cols = [c for c in golden.columns if c in live.columns]
    merged = golden[cols].merge(
        live[cols], on=["method", "budget", "corruption_rate"], suffixes=("_g", "_n")
    )
    numeric = [
        c
        for c in cols
        if c not in {"method"} and pd.api.types.is_numeric_dtype(golden[c])
    ]
    for col in numeric:
        if col in {"budget", "corruption_rate"}:
            continue
        delta = (merged[f"{col}_g"] - merged[f"{col}_n"]).abs().max()
        assert delta < 1e-9, f"{col} max abs delta {delta}"
    inject = live[(live["budget"] == 0.30) & (live["corruption_rate"] == 0.30)]
    retained = dict(zip(inject["method"], inject["n_corrupt_retained"]))
    assert int(retained["EgoSelect"]) == 3
    assert int(retained["Dedup-only"]) == 4
    assert int(retained["Diversity-only"]) == 7
    assert int(retained["Random"]) == 8
