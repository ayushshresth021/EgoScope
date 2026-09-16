"""Template-based decision brief. Numbers come only from analysis JSON."""

from __future__ import annotations

from typing import Any


def _pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.3f}"


def _metric(row: dict[str, Any] | None, key: str) -> str:
    if not row:
        return "n/a"
    val = row.get(key)
    if isinstance(val, dict):
        return (
            f"{val['mean']:.3f} (range {val['min']:.3f}–{val['max']:.3f})"
        )
    if val is None:
        return "n/a"
    return f"{float(val):.3f}"


def render_brief(analysis: dict[str, Any]) -> str:
    scope = analysis["confirmed_scope"]
    rec = analysis["recommendation"]
    feas = analysis["feasibility"]
    evidence = analysis.get("primary_metrics") or {}
    methods = analysis.get("method_rows") or []
    unsupported = analysis.get("unsupported") or []
    proxies = analysis.get("proxies") or []
    trade = analysis.get("tradeoff") or ""
    next_step = analysis.get("next_validation_step") or (
        "Validate the selected subset with a held-out downstream evaluation; "
        "this brief does not measure policy success."
    )

    method_lines = []
    for row in methods:
        method_lines.append(
            f"- {row['method']}: coverage {_metric(row, 'behavioral_region_coverage')}, "
            f"quality {_metric(row, 'average_quality')}, "
            f"redundancy {_metric(row, 'nn_redundancy')}"
        )

    proxy_lines = [f"- {p}" for p in proxies] or ["- None"]
    unsup_lines = [f"- {u}" for u in unsupported] or [
        "- None recorded for this request"
    ]
    constraint_lines = []
    for step in feas.get("constraint_steps") or []:
        if step.get("constraint") == "all":
            constraint_lines.append(f"- Universe: {step['n_remaining']} episodes")
        else:
            constraint_lines.append(
                f"- After {step.get('field')} {step.get('operator')} "
                f"{step.get('value')}: {step['n_remaining']} eligible "
                f"({step.get('removed', 0)} removed)"
            )

    budget = scope.get("budget") or {}
    rec_text = rec.get("reason") or "No recommendation."
    if rec.get("method"):
        rec_text = f"Use the {rec['method']} subset. {rec_text}"

    return f"""# Curation Decision Brief

## Request
{scope.get("original_request", "").strip()}

## Interpreted scope
- Request type: {scope.get("request_type")}
- Budget: {budget.get("value")} {budget.get("unit")} (source: {budget.get("source")})
- Priority profile: {rec.get("profile")}
- Hard constraints: {len(scope.get("hard_constraints") or [])}

## Feasibility
- Eligible episodes: {feas.get("n_eligible")} of {feas.get("n_universe")}
- Feasible: {feas.get("feasible")}
{chr(10).join(constraint_lines) if constraint_lines else "- No hard filters applied."}

## Recommendation
{rec_text}

## Evidence
- Measured region coverage: {_metric(evidence, "behavioral_region_coverage")}
- Measured average quality: {_metric(evidence, "average_quality")}
- Measured redundancy: {_metric(evidence, "nn_redundancy")}
- Eligible episodes after constraints: {feas.get("n_eligible")}
- Episodes retained: {evidence.get("n_keep", "n/a")}

## Baseline comparison
{chr(10).join(method_lines) if method_lines else "- No baseline comparison for this request type."}

## Trade-off
{trade or "See measured method table."}

## Proxy and unsupported requirements
Proxies:
{chr(10).join(proxy_lines)}

Unsupported:
{chr(10).join(unsup_lines)}

## Confidence
{rec.get("confidence", "moderate").title()}. The recommendation uses intrinsic dataset metrics. Coverage regions are unsupervised visual-motion partitions, and downstream policy performance was not tested.

## Best next validation step
{next_step}

## Unsupported conclusion
This analysis does not establish that the selected subset will preserve or improve robot-policy success.
"""
