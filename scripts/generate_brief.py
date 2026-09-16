#!/usr/bin/env python3
"""Print or regenerate the Markdown decision brief for a saved run."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from analysis.brief import render_brief  # noqa: E402
from egoscope.pipeline import load_run  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id")
    parser.add_argument("--rewrite", action="store_true")
    args = parser.parse_args()
    result = load_run(args.run_id)
    brief = render_brief(result["analysis"])
    if args.rewrite:
        Path(result["dir"]).joinpath("decision_brief.md").write_text(brief)
    print(brief)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
