"""Small JSON helpers used by scripts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def dump_json(payload: Any, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path
