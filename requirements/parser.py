"""Natural-language request parser.

Fixture matches and heuristics run without an LLM. An optional OpenAI-compatible
client may propose JSON that is still schema- and registry-validated.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any

from requirements.feasibility import assess_scope
from requirements.registry import unsupported_concepts
from requirements.schema import (
    Budget,
    ExtractedRequirement,
    HardConstraint,
    Objective,
    PriorityLevel,
    RequestType,
    RequirementStatus,
    Scope,
    ScopeProposal,
    SoftPriorities,
    SourceKind,
)

SEMANTIC_HINTS = (
    "drawer",
    "cup",
    "saucer",
    "fold clothes",
    "ironing",
    "dishwasher",
    "plant",
    "object",
    "open the",
)
ENVIRONMENT_HINTS = ("kitchen", "environment", "lab named", "scene named")
POLICY_HINTS = (
    "policy",
    "diffusion",
    "success rate",
    "downstream",
    "train the robot",
    "maximize success",
    "policy performance",
    "policy success",
    "improve diffusion",
)
CUSTOMER_HINTS = ("customer acceptance", "sla", "customer")
INJECTION_HINTS = (
    "task_success",
    "create a feature",
    "new column",
    "add field",
    "label_score",
    "recovery_event",
    "invent a",
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _rid() -> str:
    return f"REQ-{uuid.uuid4().hex[:8].upper()}"


def _priority_from_text(text: str) -> SoftPriorities:
    t = _norm(text)
    quality = PriorityLevel.medium
    coverage = PriorityLevel.medium
    redundancy = PriorityLevel.medium
    if "broad" in t or ("coverage" in t and ("more than redundancy" in t or "prioritize" in t)):
        coverage = PriorityLevel.high
    if "quality-first" in t or "quality first" in t or "highest quality" in t:
        quality = PriorityLevel.high
    if "dedup" in t and "coverage" not in t:
        redundancy = PriorityLevel.high
    if "balancing" in t or "balanced" in t:
        quality = coverage = redundancy = PriorityLevel.medium
    if "coverage matters more" in t:
        coverage = PriorityLevel.high
        redundancy = PriorityLevel.medium
    return SoftPriorities(
        quality=quality, coverage=coverage, redundancy_reduction=redundancy
    )


def _extract_budget(text: str) -> Budget:
    t = _norm(text)
    count = re.search(r"\bkeep\s+(\d{1,3})\s+episodes?\b", t)
    if not count:
        count = re.search(r"\b(\d{1,3})\s+episodes\b", t)
    if count:
        return Budget(
            unit="episodes",
            value=float(count.group(1)),
            source=SourceKind.explicit,
        )
    vs = re.search(
        r"(\d{1,3})\s*%\s*(?:versus|vs\.?|vs|instead of)\s*(\d{1,3})\s*%",
        t,
    )
    percents = [
        float(x) / 100.0
        for x in re.findall(r"\b(\d{1,3})\s*%(?!\s+stationary)", t)
    ]
    if vs:
        a, b = float(vs.group(1)) / 100.0, float(vs.group(2)) / 100.0
        return Budget(
            unit="episode_fraction",
            value=max(a, b),
            compare_with=min(a, b),
            source=SourceKind.explicit,
        )
    if len(percents) >= 2 and (
        "instead of" in t or "versus" in t or " vs" in t or "compare" in t
    ):
        return Budget(
            unit="episode_fraction",
            value=max(percents[0], percents[1]),
            compare_with=min(percents[0], percents[1]),
            source=SourceKind.explicit,
        )
    if percents:
        return Budget(
            unit="episode_fraction",
            value=percents[0],
            source=SourceKind.explicit,
        )
    return Budget()


def _idle_constraint(text: str) -> HardConstraint | None:
    t = _norm(text)
    ratio = re.search(r"stationary(?:_ratio)?\s*(?:<=|≤|less than or equal to)\s*([0-9.]+)", t)
    if ratio:
        raw = float(ratio.group(1))
        value = raw / 100.0 if raw > 1 else raw
        return HardConstraint(
            requirement_id="R-idle",
            concept="maximum_stationary_ratio",
            field="stationary_ratio",
            operator="less_than_or_equal",
            value=value,
            source=SourceKind.explicit,
            signal="avoid_idle",
        )
    if "stationary" not in t and "idle" not in t:
        return None
    m = re.search(r"(\d{1,3})\s*%\s+stationary", t)
    if m:
        value = float(m.group(1)) / 100.0
        source = SourceKind.explicit
    elif "idle" in t:
        value = 0.25
        source = SourceKind.assumed
    else:
        return None
    return HardConstraint(
        requirement_id="R-idle",
        concept="maximum_stationary_ratio",
        field="stationary_ratio",
        operator="less_than_or_equal",
        value=value,
        source=source,
        signal="avoid_idle",
    )


def _request_type(text: str) -> RequestType:
    t = _norm(text)
    if any(h in t for h in POLICY_HINTS):
        return RequestType.unsupported_or_unknown
    if any(h in t for h in CUSTOMER_HINTS):
        return RequestType.unsupported_or_unknown
    if "invent a" in t and not re.search(r"\b\d+\s*%", t):
        return RequestType.unsupported_or_unknown
    if any(h in t for h in SEMANTIC_HINTS):
        if "keep" in t and re.search(r"\d", t):
            pass
        else:
            return RequestType.unsupported_or_unknown
    if "drawer" in t and not re.search(r"\b\d+\s*%", t):
        return RequestType.unsupported_or_unknown
    if "smallest subset" in t or "every discovered" in t or "every region" in t:
        return RequestType.find_minimum_subset
    if (
        "versus" in t
        or " vs " in t
        or "compare keeping" in t
        or "instead of" in t
        or (len(re.findall(r"\b\d+\s*%", t)) >= 2 and "compare" in t)
    ):
        return RequestType.compare_budgets
    if (
        "egoselect" in t
        or "dedup-only" in t
        or "diversity-only" in t
        or "should this dataset use" in t
    ) and ("or" in t or "compare" in t or "vs" in t):
        return RequestType.compare_methods
    if ("consistently selected" in t) or (
        "quality-first" in t and "coverage-first" in t
    ):
        return RequestType.test_strategy
    if "weakness" in t or "diagnose" in t or "main weaknesses" in t:
        return RequestType.diagnose_dataset
    if "keep" in t or "select" in t or "exclude" in t:
        return RequestType.select_subset
    return RequestType.unsupported_or_unknown


def heuristic_parse(text: str) -> ScopeProposal:
    request_type = _request_type(text)
    budget = _extract_budget(text)
    idle = _idle_constraint(text)
    priorities = _priority_from_text(text)
    t = _norm(text)
    reqs: list[ExtractedRequirement] = []
    assumptions: list[str] = []

    if budget.value is not None:
        reqs.append(
            ExtractedRequirement(
                requirement_id="R-budget",
                text=f"Keep {budget.value} {budget.unit}",
                status=RequirementStatus.direct,
                signal="episode_budget",
                source=budget.source,
            )
        )
    elif request_type in {
        RequestType.select_subset,
        RequestType.compare_methods,
        RequestType.test_strategy,
    }:
        reqs.append(
            ExtractedRequirement(
                requirement_id="R-budget",
                text="budget",
                status=RequirementStatus.missing_information,
                signal="episode_budget",
                missing="budget",
            )
        )

    if idle:
        reqs.append(
            ExtractedRequirement(
                requirement_id=idle.requirement_id,
                text=f"stationary_ratio <= {idle.value}",
                status=RequirementStatus.direct,
                signal="avoid_idle",
                field="stationary_ratio",
                source=idle.source,
            )
        )
        if idle.source == SourceKind.assumed:
            assumptions.append(
                f"Idle-heavy is interpreted as stationary_ratio > {idle.value}"
            )

    if "coverage" in t or "broad" in t or request_type == RequestType.find_minimum_subset:
        reqs.append(
            ExtractedRequirement(
                requirement_id="R-coverage",
                text="representation coverage",
                status=RequirementStatus.proxy,
                signal="visual_motion_coverage",
                field="behavioral_region",
            )
        )
        assumptions.append(
            "Behavioral coverage is approximated by unsupervised representation regions"
        )

    if "redundan" in t or "dedup" in t:
        reqs.append(
            ExtractedRequirement(
                requirement_id="R-redundancy",
                text="reduce redundancy",
                status=RequirementStatus.proxy,
                signal="reduce_redundancy",
            )
        )

    if "quality" in t or "balancing" in t:
        reqs.append(
            ExtractedRequirement(
                requirement_id="R-quality",
                text="quality",
                status=RequirementStatus.direct,
                signal="general_quality",
                field="quality_score",
            )
        )

    if any(h in t for h in SEMANTIC_HINTS) or "drawer" in t:
        reqs.append(
            ExtractedRequirement(
                requirement_id="R-semantic",
                text="semantic task or object filter",
                status=RequirementStatus.unsupported,
                unsupported_concept="semantic_task",
            )
        )
        request_type = (
            request_type
            if budget.value is not None
            else RequestType.unsupported_or_unknown
        )

    if any(h in t for h in ENVIRONMENT_HINTS):
        reqs.append(
            ExtractedRequirement(
                requirement_id="R-env",
                text="environment filter",
                status=RequirementStatus.unsupported,
                unsupported_concept="environment_identity",
            )
        )

    if any(h in t for h in CUSTOMER_HINTS):
        reqs.append(
            ExtractedRequirement(
                requirement_id="R-customer",
                text="customer acceptance",
                status=RequirementStatus.unsupported,
                unsupported_concept="customer_acceptance",
            )
        )
        request_type = RequestType.unsupported_or_unknown

    if any(h in t for h in POLICY_HINTS):
        reqs.append(
            ExtractedRequirement(
                requirement_id="R-policy",
                text="policy success",
                status=RequirementStatus.prohibited,
                unsupported_concept="policy_improvement",
            )
        )
        request_type = RequestType.unsupported_or_unknown

    if any(h in t for h in INJECTION_HINTS):
        reqs.append(
            ExtractedRequirement(
                requirement_id="R-inject",
                text="requested unregistered field",
                status=RequirementStatus.unsupported,
                unsupported_concept="invented_feature",
            )
        )

    if request_type == RequestType.test_strategy:
        strategy_profiles = ["balanced", "quality_first", "coverage_first"]
        if budget.value is None:
            budget = Budget(
                unit="episode_fraction",
                value=0.30,
                source=SourceKind.default,
            )
            assumptions.append("Default budget of 30% used for strategy comparison")
            reqs = [r for r in reqs if r.missing != "budget"]
            reqs.append(
                ExtractedRequirement(
                    requirement_id="R-budget",
                    text="Keep 0.3 episode_fraction",
                    status=RequirementStatus.direct,
                    signal="episode_budget",
                    source=SourceKind.default,
                )
            )
    else:
        strategy_profiles = []

    if request_type == RequestType.compare_methods and budget.value is None:
        budget = Budget(
            unit="episode_fraction",
            value=0.30,
            source=SourceKind.default,
        )
        assumptions.append("Default budget of 30% used for method comparison")
        reqs = [r for r in reqs if r.missing != "budget"]
        reqs.append(
            ExtractedRequirement(
                requirement_id="R-budget",
                text="Keep 0.3 episode_fraction",
                status=RequirementStatus.direct,
                signal="episode_budget",
                source=SourceKind.default,
            )
        )

    if request_type == RequestType.find_minimum_subset:
        budget = Budget()

    if request_type == RequestType.compare_methods:
        comparisons = ["dedup_only"]
        if "diversity" in t:
            comparisons.append("diversity_only")
        if "random" in t:
            comparisons.append("random")
    else:
        comparisons = ["random", "dedup_only", "diversity_only"]

    descriptions = {
        RequestType.select_subset: "Create a reduced subset under confirmed constraints",
        RequestType.find_minimum_subset: "Find the smallest prefix that covers every discovered region",
        RequestType.compare_budgets: "Compare two keep budgets on measured metrics",
        RequestType.compare_methods: "Compare EgoSelect with requested baselines",
        RequestType.diagnose_dataset: "Diagnose quality, imbalance, and redundancy in the pool",
        RequestType.test_strategy: "Compare selection overlap across weight profiles",
        RequestType.unsupported_or_unknown: "No executable curation objective from available evidence",
    }
    scope = Scope(
        request_id=_rid(),
        original_request=text,
        request_type=request_type,
        objective=Objective(description=descriptions[request_type]),
        budget=budget,
        hard_constraints=[idle] if idle else [],
        soft_priorities=priorities,
        comparisons=comparisons,
        assumptions=assumptions,
        strategy_profiles=strategy_profiles,
    )
    return assess_scope(scope, reqs)


def _llm_parse(text: str) -> dict[str, Any] | None:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        import httpx
    except ImportError:
        return None
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.environ.get("EGOSCOPE_MODEL", "gpt-4o-mini")
    schema_hint = {
        "request_type": [e.value for e in RequestType],
        "budget": {"unit": ["episodes", "episode_fraction"], "value": "number or null"},
        "hard_constraints": [
            {
                "concept": "maximum_stationary_ratio",
                "field": "stationary_ratio",
                "operator": "less_than_or_equal",
                "value": 0.25,
            }
        ],
        "soft_priorities": {"quality": "low|medium|high", "coverage": "", "redundancy_reduction": ""},
        "signals_only": list(unsupported_concepts().keys()),
    }
    prompt = (
        "Extract an EgoScope curation scope as JSON. Use only registered signals. "
        "Never invent feature columns. Never claim policy improvement. "
        f"Schema hint: {json.dumps(schema_hint)}\nRequest: {text}"
    )
    try:
        resp = httpx.post(
            f"{base.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": "Return JSON only. Do not invent dataset fields.",
                    },
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception:
        return None


def parse_request(text: str) -> ScopeProposal:
    original = text
    text = text.strip()
    if not text:
        raise ValueError("Request is empty")
    proposal = heuristic_parse(original)
    llm = _llm_parse(original)
    if not llm:
        return proposal
    # LLM may refine type/budget/priorities but cannot add unregistered fields.
    try:
        if "request_type" in llm:
            proposal.proposed_scope.request_type = RequestType(llm["request_type"])
        if isinstance(llm.get("budget"), dict) and llm["budget"].get("value") is not None:
            proposal.proposed_scope.budget = Budget(
                unit=llm["budget"].get("unit") or proposal.proposed_scope.budget.unit,
                value=float(llm["budget"]["value"]),
                source=SourceKind.explicit,
                compare_with=llm["budget"].get("compare_with"),
            )
        return assess_scope(proposal.proposed_scope, proposal.requirements)
    except Exception:
        return proposal
