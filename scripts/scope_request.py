#!/usr/bin/env python3
"""Parse a natural-language curation request into a proposed scope."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from egoscope.pipeline import propose_scope  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", nargs="?", help="Natural-language curation request")
    parser.add_argument("--file", type=Path, help="Read request text from a file")
    args = parser.parse_args()
    text = args.request
    if args.file:
        text = args.file.read_text()
    if not text or not text.strip():
        print("Empty requests cannot be submitted.", file=sys.stderr)
        return 1
    proposal = propose_scope(text)
    print(json.dumps(proposal.model_dump(mode="json"), indent=2))
    return 0 if proposal.can_execute else 2


if __name__ == "__main__":
    raise SystemExit(main())
