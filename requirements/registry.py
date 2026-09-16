"""Signal registry: the trust boundary between language and execution."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "configs" / "signal_registry.yaml"
PROFILES_PATH = ROOT / "configs" / "strategy_profiles.yaml"

ALLOWED_OPERATORS = {
    "<=": "less_than_or_equal",
    "less_than_or_equal": "less_than_or_equal",
    "<": "less_than",
    "less_than": "less_than",
    ">=": "greater_than_or_equal",
    "greater_than_or_equal": "greater_than_or_equal",
    ">": "greater_than",
    "greater_than": "greater_than",
    "minimize": "minimize",
}

EXECUTABLE_FIELDS = {
    "stationary_ratio",
    "quality_score",
    "quality_valid_frame_ratio",
    "quality_trajectory_completeness",
    "quality_finite_pose_ratio",
    "quality_temporal_validity",
    "quality_nonstationary",
    "path_length",
    "mean_speed",
    "speed_std",
    "direction_change_ratio",
    "behavioral_region",
}


@lru_cache(maxsize=1)
def load_registry() -> dict[str, Any]:
    return yaml.safe_load(REGISTRY_PATH.read_text())


@lru_cache(maxsize=1)
def load_profiles() -> dict[str, Any]:
    return yaml.safe_load(PROFILES_PATH.read_text())


def signals() -> dict[str, Any]:
    return load_registry()["signals"]


def unsupported_concepts() -> dict[str, str]:
    return load_registry()["unsupported_concepts"]


def is_registered_signal(name: str) -> bool:
    return name in signals()


def is_registered_field(field: str) -> bool:
    if field in EXECUTABLE_FIELDS:
        return True
    for spec in signals().values():
        if spec.get("field") == field:
            return True
        if field in (spec.get("fields") or []):
            return True
    return False


def normalize_operator(op: str) -> str:
    key = op.strip().lower()
    if key not in ALLOWED_OPERATORS:
        raise ValueError(f"Operator {op!r} is not allowed")
    return ALLOWED_OPERATORS[key]


def signal_for_field(field: str) -> str | None:
    for name, spec in signals().items():
        if spec.get("field") == field:
            return name
        if field in (spec.get("fields") or []):
            return name
    return None
