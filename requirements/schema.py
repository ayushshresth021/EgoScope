"""Structured scope schema for EgoScope requests."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class RequestType(str, Enum):
    select_subset = "select_subset"
    find_minimum_subset = "find_minimum_subset"
    compare_budgets = "compare_budgets"
    compare_methods = "compare_methods"
    diagnose_dataset = "diagnose_dataset"
    test_strategy = "test_strategy"
    unsupported_or_unknown = "unsupported_or_unknown"


class PriorityLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class RequirementStatus(str, Enum):
    direct = "direct"
    proxy = "proxy"
    missing_information = "missing_information"
    unsupported = "unsupported"
    prohibited = "prohibited"


class SourceKind(str, Enum):
    explicit = "explicit"
    assumed = "assumed"
    default = "default"


class Budget(BaseModel):
    unit: Literal["episodes", "episode_fraction"] | None = None
    value: float | None = None
    source: SourceKind | None = None
    compare_with: float | None = None


class HardConstraint(BaseModel):
    requirement_id: str
    concept: str
    field: str
    operator: str
    value: float
    source: SourceKind
    signal: str | None = None


class SoftPriorities(BaseModel):
    quality: PriorityLevel = PriorityLevel.medium
    coverage: PriorityLevel = PriorityLevel.medium
    redundancy_reduction: PriorityLevel = PriorityLevel.medium


class RunOptions(BaseModel):
    random_seed: int = 42
    number_of_regions: int = 6


class Objective(BaseModel):
    description: str = ""


class Scope(BaseModel):
    scope_version: str = "1.0"
    request_id: str
    original_request: str
    request_type: RequestType
    objective: Objective = Field(default_factory=Objective)
    budget: Budget = Field(default_factory=Budget)
    hard_constraints: list[HardConstraint] = Field(default_factory=list)
    soft_priorities: SoftPriorities = Field(default_factory=SoftPriorities)
    comparisons: list[str] = Field(
        default_factory=lambda: ["random", "dedup_only", "diversity_only"]
    )
    run_options: RunOptions = Field(default_factory=RunOptions)
    assumptions: list[str] = Field(default_factory=list)
    requested_outputs: list[str] = Field(
        default_factory=lambda: [
            "selected_manifest",
            "baseline_comparison",
            "decision_brief",
        ]
    )
    strategy_profiles: list[str] = Field(default_factory=list)

    @field_validator("comparisons")
    @classmethod
    def _normalize_comparisons(cls, values: list[str]) -> list[str]:
        allowed = {
            "random",
            "dedup_only",
            "diversity_only",
            "egoselect",
            "dedup",
            "diversity",
        }
        out = []
        for item in values:
            key = item.strip().lower().replace("-", "_").replace(" ", "_")
            if key in {"dedup"}:
                key = "dedup_only"
            if key in {"diversity"}:
                key = "diversity_only"
            if key not in allowed and key != "egoselect":
                continue
            if key not in out:
                out.append(key)
        return out or ["random", "dedup_only", "diversity_only"]


class ExtractedRequirement(BaseModel):
    requirement_id: str
    text: str
    status: RequirementStatus
    signal: str | None = None
    field: str | None = None
    missing: str | None = None
    limitation: str | None = None
    unsupported_concept: str | None = None
    source: SourceKind | None = None


class ScopeProposal(BaseModel):
    proposed_scope: Scope
    requirements: list[ExtractedRequirement]
    can_execute: bool
    blocking_reasons: list[str] = Field(default_factory=list)

    def model_dump_public(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
