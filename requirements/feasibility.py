"""Classify extracted requirements against the signal registry."""

from __future__ import annotations

from requirements.registry import (
    is_registered_field,
    is_registered_signal,
    signals,
    unsupported_concepts,
)
from requirements.schema import (
    ExtractedRequirement,
    RequestType,
    RequirementStatus,
    Scope,
    ScopeProposal,
)


PROXY_LIMITATIONS = {
    "visual_motion_coverage": (
        "Behavioral coverage is approximated by unsupervised visual-motion "
        "regions. These are not semantic robot skills."
    ),
    "reduce_redundancy": (
        "Redundancy is nearest-neighbor cosine similarity in representation "
        "space, not duplicate task labels."
    ),
    "motion_variety": (
        "Motion variety uses trajectory statistics, not named behaviors."
    ),
}


def classify_requirement(req: ExtractedRequirement) -> ExtractedRequirement:
    if req.unsupported_concept and req.unsupported_concept in unsupported_concepts():
        reason = unsupported_concepts()[req.unsupported_concept]
        status = (
            RequirementStatus.prohibited
            if req.unsupported_concept == "policy_improvement"
            else RequirementStatus.unsupported
        )
        return req.model_copy(
            update={
                "status": status,
                "limitation": reason,
                "signal": None,
                "field": None,
            }
        )
    if req.signal and not is_registered_signal(req.signal):
        return req.model_copy(
            update={
                "status": RequirementStatus.unsupported,
                "unsupported_concept": "invented_feature",
                "limitation": unsupported_concepts()["invented_feature"],
                "signal": None,
                "field": None,
            }
        )
    if req.field and not is_registered_field(req.field):
        return req.model_copy(
            update={
                "status": RequirementStatus.unsupported,
                "unsupported_concept": "invented_feature",
                "limitation": unsupported_concepts()["invented_feature"],
                "field": None,
            }
        )
    if req.signal:
        spec = signals()[req.signal]
        support = spec.get("support", "direct")
        if support.startswith("proxy"):
            return req.model_copy(
                update={
                    "status": RequirementStatus.proxy,
                    "limitation": PROXY_LIMITATIONS.get(req.signal, spec.get("limitation")),
                    "field": req.field or spec.get("field"),
                }
            )
        if req.status == RequirementStatus.missing_information:
            return req
        return req.model_copy(
            update={
                "status": RequirementStatus.direct,
                "field": req.field or spec.get("field"),
            }
        )
    if req.status in {
        RequirementStatus.unsupported,
        RequirementStatus.prohibited,
        RequirementStatus.missing_information,
    }:
        return req
    return req.model_copy(update={"status": RequirementStatus.unsupported})


def assess_scope(scope: Scope, requirements: list[ExtractedRequirement]) -> ScopeProposal:
    classified = [classify_requirement(req) for req in requirements]
    blocking: list[str] = []
    executable_statuses = {
        RequirementStatus.direct,
        RequirementStatus.proxy,
    }
    has_executable = any(r.status in executable_statuses for r in classified)
    missing = [r for r in classified if r.status == RequirementStatus.missing_information]
    unsupported = [
        r
        for r in classified
        if r.status in {RequirementStatus.unsupported, RequirementStatus.prohibited}
    ]

    needs_budget = scope.request_type in {
        RequestType.select_subset,
        RequestType.compare_methods,
        RequestType.test_strategy,
    }
    if needs_budget and (scope.budget.value is None or scope.budget.unit is None):
        if not any(r.missing == "budget" for r in missing):
            missing.append(
                ExtractedRequirement(
                    requirement_id="budget",
                    text="budget",
                    status=RequirementStatus.missing_information,
                    signal="episode_budget",
                    missing="budget",
                )
            )
            classified.append(missing[-1])
        blocking.append("Budget is required before execution.")

    if scope.request_type == RequestType.compare_budgets:
        if scope.budget.value is None or scope.budget.compare_with is None:
            blocking.append("Two budgets are required for a budget comparison.")

    if scope.request_type == RequestType.unsupported_or_unknown and not has_executable:
        blocking.append("No executable alternative remains after unsupported requirements.")

    if unsupported and not has_executable and scope.request_type not in {
        RequestType.diagnose_dataset,
        RequestType.find_minimum_subset,
    }:
        blocking.append("Request has no supported executable objective.")

    can_execute = not blocking and scope.request_type != RequestType.unsupported_or_unknown
    if scope.request_type == RequestType.find_minimum_subset:
        can_execute = not blocking
    if scope.request_type == RequestType.diagnose_dataset:
        can_execute = True
    if has_executable and scope.request_type == RequestType.unsupported_or_unknown:
        can_execute = not blocking
    if missing and needs_budget:
        can_execute = False

    blocking = list(dict.fromkeys(blocking))
    return ScopeProposal(
        proposed_scope=scope,
        requirements=classified,
        can_execute=can_execute,
        blocking_reasons=blocking,
    )
