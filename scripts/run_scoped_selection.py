#!/usr/bin/env python3
"""Confirm a scope JSON document and run EgoSelect plus baselines."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from egoscope.pipeline import propose_scope, run_confirmed  # noqa: E402
from requirements.schema import Scope  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", nargs="?", help="Natural-language request")
    parser.add_argument("--scope", type=Path, help="Confirmed scope JSON")
    parser.add_argument(
        "--print-scope-only",
        action="store_true",
        help="Parse and print the proposed scope without running",
    )
    args = parser.parse_args()

    if args.scope:
        payload = json.loads(args.scope.read_text())
        scope = Scope.model_validate(payload.get("proposed_scope", payload))
        proposal = propose_scope(scope.original_request)
        proposal.proposed_scope = scope
        proposal = proposal.model_copy(update={"proposed_scope": scope})
    else:
        if not args.request or not args.request.strip():
            print("A request or --scope file is required.", file=sys.stderr)
            return 1
        proposal = propose_scope(args.request)
        scope = proposal.proposed_scope
        if args.print_scope_only:
            print(json.dumps(proposal.model_dump(mode="json"), indent=2))
            return 0 if proposal.can_execute else 2

    result = run_confirmed(scope, proposed=proposal)
    print(json.dumps({"run_id": result["run_id"], "dir": result["dir"]}, indent=2))
    rec = result["analysis"]["recommendation"]
    print(rec.get("reason", ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
