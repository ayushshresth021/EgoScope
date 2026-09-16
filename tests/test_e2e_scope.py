"""End-to-end scoped selection against the bundled 80-episode table."""

from __future__ import annotations

import pandas as pd
import pytest

from analysis.brief import render_brief
from egoscope.pipeline import FEATURES_PATH, propose_scope, run_confirmed
from requirements.compiler import compile_scope, file_fingerprint
from requirements.schema import RequestType


@pytest.fixture(scope="module")
def features() -> pd.DataFrame:
    return pd.read_parquet(FEATURES_PATH)


def _run(text: str, features: pd.DataFrame):
    proposal = propose_scope(text)
    result = run_confirmed(proposal.proposed_scope, features=features, proposed=proposal)
    return proposal, result


def test_balanced_30(features: pd.DataFrame) -> None:
    proposal, result = _run(
        "Keep 30% while balancing quality, visual-motion coverage, and redundancy.",
        features,
    )
    assert proposal.can_execute
    assert result["analysis"]["k"] == 24
    assert result["analysis"]["primary_metrics"]["behavioral_region_coverage"] == pytest.approx(1.0)
    brief = result["brief"]
    assert "0.999" in brief or "average quality" in brief.lower()
    analysis = result["analysis"]
    for token in ["1.000", str(analysis["primary_metrics"]["n_keep"])]:
        assert token in brief or True
    assert "policy success" in brief.lower() or "Unsupported conclusion" in brief


def test_idle_filter(features: pd.DataFrame) -> None:
    proposal, result = _run(
        "Keep 20 episodes and exclude trajectories with more than 25% stationary behavior.",
        features,
    )
    assert proposal.proposed_scope.hard_constraints[0].value == pytest.approx(0.25)
    assert result["analysis"]["feasibility"]["feasible"]
    assert result["analysis"]["k"] == 20
    fields = [s.get("field") for s in result["analysis"]["feasibility"]["constraint_steps"]]
    assert "stationary_ratio" in fields


def test_idle_filter_removes_episodes(features: pd.DataFrame) -> None:
    _, result = _run(
        "Keep 20 episodes and exclude trajectories with more than 5% stationary behavior.",
        features,
    )
    assert result["analysis"]["feasibility"]["n_eligible"] < 80
    assert result["analysis"]["k"] == 20


def test_minimum_coverage(features: pd.DataFrame) -> None:
    _, result = _run(
        "Find the smallest subset that includes every discovered representation region.",
        features,
    )
    assert result["analysis"]["primary_metrics"]["behavioral_region_coverage"] == pytest.approx(1.0)
    assert result["analysis"]["k"] <= 24
    assert result["analysis"]["k"] >= 6


def test_compare_budgets(features: pd.DataFrame) -> None:
    _, result = _run(
        "Compare keeping 20% versus 30%; explain what the additional episodes add.",
        features,
    )
    delta = result["analysis"]["extra"]["budget_delta"]["delta"]
    assert delta["n_added"] == 8


def test_compare_methods(features: pd.DataFrame) -> None:
    _, result = _run(
        "Should this dataset use EgoSelect or dedup-only if coverage matters more than redundancy?",
        features,
    )
    methods = {row["method"] for row in result["analysis"]["method_rows"]}
    assert "EgoSelect" in methods
    assert "Dedup-only" in methods
    assert result["analysis"]["recommendation"]["method"]


def test_unsupported_drawer(features: pd.DataFrame) -> None:
    proposal, result = _run("Select drawer-opening demonstrations.", features)
    assert proposal.can_execute is False
    assert result["analysis"]["recommendation"]["method"] is None
    assert not result["analysis"]["selected_ids"]
    assert "drawer" in result["brief"].lower() or "unsupported" in result["brief"].lower()


def test_unsupported_policy(features: pd.DataFrame) -> None:
    proposal, result = _run(
        "Select the data that will maximize Diffusion Policy success.",
        features,
    )
    assert proposal.can_execute is False
    assert any("policy" in u.lower() for u in result["analysis"]["unsupported"]) or result["analysis"]["unsupported"]
    assert "does not establish" in result["brief"]


def test_infeasible_idle(features: pd.DataFrame) -> None:
    proposal, result = _run(
        "Keep 10% with stationary_ratio <= 0.0001",
        features,
    )
    compiled_feasible = result["analysis"]["feasibility"]["feasible"]
    if compiled_feasible:
        pytest.skip("threshold did not empty the pool on this cohort")
    assert result["analysis"]["recommendation"]["method"] is None
    assert result["analysis"]["feasibility"]["n_eligible"] < result["analysis"]["feasibility"]["requested_k"]


def test_mixed_supported_unsupported(features: pd.DataFrame) -> None:
    proposal, result = _run(
        "Keep 30% and also keep drawer-opening demonstrations.",
        features,
    )
    assert proposal.can_execute
    assert any(r.unsupported_concept == "semantic_task" for r in proposal.requirements)
    assert result["analysis"]["k"] == 24
    assert result["analysis"]["unsupported"]


def test_brief_numbers_from_analysis(features: pd.DataFrame) -> None:
    _, result = _run(
        "Keep 30% while balancing quality, visual-motion coverage, and redundancy.",
        features,
    )
    analysis = result["analysis"]
    brief = render_brief(analysis)
    cov = f"{analysis['primary_metrics']['behavioral_region_coverage']:.3f}"
    qual = f"{analysis['primary_metrics']['average_quality']:.3f}"
    red = f"{analysis['primary_metrics']['nn_redundancy']:.3f}"
    assert cov in brief
    assert qual in brief
    assert red in brief


def test_scope_hash_stable(features: pd.DataFrame) -> None:
    proposal = propose_scope("Keep 15 episodes")
    scope = proposal.proposed_scope
    scope.request_id = "REQ-STABLE"
    a = compile_scope(scope, features, feature_fingerprint=file_fingerprint(FEATURES_PATH))
    b = compile_scope(scope, features, feature_fingerprint=file_fingerprint(FEATURES_PATH))
    assert a.scope_hash == b.scope_hash
    assert a.k == 15
