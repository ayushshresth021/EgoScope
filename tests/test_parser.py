"""Parser and feasibility fixtures. No LLM required."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from egoscope.pipeline import propose_scope, run_confirmed
from requirements.compiler import compile_scope, file_fingerprint
from requirements.parser import parse_request
from requirements.schema import RequestType, RequirementStatus, Scope

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ROOT / "outputs" / "episode_features.parquet"


CASES = yaml.safe_load(
    """
- request: Keep 30% while balancing quality, visual-motion coverage, and redundancy.
  type: select_subset
  budget: 0.3
  executable: true
- request: Keep 20 episodes and exclude trajectories with more than 25% stationary behavior.
  type: select_subset
  budget: 20
  idle: 0.25
  executable: true
- request: Find the smallest subset that includes every discovered representation region.
  type: find_minimum_subset
  executable: true
- request: Compare keeping 20% versus 30%; explain what the additional episodes add.
  type: compare_budgets
  executable: true
- request: Should this dataset use EgoSelect or dedup-only if coverage matters more than redundancy?
  type: compare_methods
  executable: true
- request: Which episodes are most consistently selected under balanced, quality-first, and coverage-first strategies?
  type: test_strategy
  executable: true
- request: Select drawer-opening demonstrations.
  type: unsupported_or_unknown
  executable: false
  unsupported: semantic_task
- request: Select the data that will maximize Diffusion Policy success.
  type: unsupported_or_unknown
  executable: false
  unsupported: policy_improvement
- request: Keep a small subset of the best demos.
  type: select_subset
  executable: false
  missing: budget
- request: Keep 30% and also keep drawer-opening demonstrations.
  type: select_subset
  executable: true
  unsupported: semantic_task
- request: Keep 10% with stationary_ratio <= 0.0001
  type: select_subset
  executable: true
  idle: 0.0001
- request: Diagnose the main weaknesses in this dataset.
  type: diagnose_dataset
  executable: true
- request: Keep 30% using task_success_rate as a new column
  type: select_subset
  executable: true
  unsupported: invented_feature
- request: Guarantee equal policy success after curation
  type: unsupported_or_unknown
  executable: false
  unsupported: policy_improvement
- request: Keep 40% and reduce redundancy
  type: select_subset
  executable: true
- request: Avoid idle-heavy episodes and keep 25%
  type: select_subset
  executable: true
- request: Compare EgoSelect and diversity-only at 30%
  type: compare_methods
  executable: true
- request: Keep 15 episodes
  type: select_subset
  executable: true
- request: Find every discovered representation region with the smallest subset
  type: find_minimum_subset
  executable: true
- request: What do I lose by keeping 20% instead of 50%
  type: compare_budgets
  executable: true
- request: Select cup on saucer episodes only
  type: unsupported_or_unknown
  executable: false
- request: Keep 30% of episodes from the kitchen environment
  type: select_subset
  executable: true
  unsupported: environment
- request: Maximize customer acceptance of the subset
  type: unsupported_or_unknown
  executable: false
- request: Keep 30% prioritize coverage
  type: select_subset
  executable: true
- request: Keep 20% versus 40%
  type: compare_budgets
  executable: true
- request: Exclude trajectories with more than 10% stationary behavior and keep 30%
  type: select_subset
  executable: true
- request: Please invent a recovery_event score and rank on it
  type: unsupported_or_unknown
  executable: false
- request: Keep 5%
  type: select_subset
  executable: true
- request: Rank episodes that will improve Diffusion Policy
  type: unsupported_or_unknown
  executable: false
- request: Keep 30% while balancing quality, coverage, and redundancy, and add field label_score
  type: select_subset
  executable: true
  unsupported: invented_feature
"""
)


@pytest.mark.parametrize("case", CASES, ids=[c["request"][:40] for c in CASES])
def test_parser_fixtures(case: dict) -> None:
    proposal = parse_request(case["request"])
    assert proposal.proposed_scope.original_request == case["request"]
    assert proposal.proposed_scope.request_type.value == case["type"]
    assert proposal.can_execute is case["executable"]
    if "budget" in case and case["budget"] >= 1:
        assert proposal.proposed_scope.budget.value == case["budget"]
    if "budget" in case and case["budget"] < 1:
        assert proposal.proposed_scope.budget.value == pytest.approx(case["budget"])
    if case.get("idle"):
        assert proposal.proposed_scope.hard_constraints
        assert proposal.proposed_scope.hard_constraints[0].value == pytest.approx(case["idle"])
    if case.get("missing") == "budget":
        assert any(r.missing == "budget" for r in proposal.requirements)
    if case.get("unsupported") == "semantic_task":
        assert any(r.unsupported_concept == "semantic_task" for r in proposal.requirements)
    if case.get("unsupported") == "policy_improvement":
        assert any(
            r.unsupported_concept == "policy_improvement"
            or r.status == RequirementStatus.prohibited
            for r in proposal.requirements
        )
    if case.get("unsupported") == "invented_feature":
        assert any(
            r.unsupported_concept == "invented_feature" or "label_score" in r.text or "task_success" in case["request"]
            for r in proposal.requirements
        )
    fields = [c.field for c in proposal.proposed_scope.hard_constraints]
    assert "task_success_rate" not in fields
    assert "label_score" not in fields


def test_empty_request_rejected() -> None:
    with pytest.raises(ValueError):
        parse_request("   ")
