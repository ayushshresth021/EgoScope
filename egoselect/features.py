"""Per-episode visual, motion, and quality feature contracts.

Phase 1 ranking reads these columns from the vendored parquet. Raw EgoVerse
ingest, JPEG decoding, and DINOv2 encoding are out of scope.
"""

from __future__ import annotations

from typing import Any

import numpy as np

N_RGB_FRAMES = 8
DINO_MODEL_ID = "facebook/dinov2-small"
STATIONARY_SPEED_MPS = 0.02
DIRECTION_CHANGE_RAD = float(np.deg2rad(30.0))
INVALID_POSE_ABS = 1e6

MOTION_COLUMNS = (
    "path_length",
    "displacement",
    "mean_speed",
    "speed_std",
    "max_speed",
    "mean_abs_accel",
    "direction_change_ratio",
    "stationary_ratio",
    "duration_s",
    "n_frames",
)

QUALITY_COLUMNS = (
    "quality_score",
    "quality_valid_frame_ratio",
    "quality_trajectory_completeness",
    "quality_finite_pose_ratio",
    "quality_nonstationary",
    "quality_temporal_validity",
)


def sample_frame_indices(n_frames: int, n_samples: int = N_RGB_FRAMES) -> np.ndarray:
    if n_frames <= 0:
        return np.zeros(0, dtype=int)
    n = min(int(n_samples), int(n_frames))
    idx = np.linspace(0, n_frames - 1, n)
    return np.unique(np.rint(idx).astype(int))


def _xyz_trajectory(pose: np.ndarray | None) -> np.ndarray:
    if pose is None or pose.size == 0:
        return np.zeros((0, 3), dtype=np.float64)
    xyz = np.asarray(pose[:, :3], dtype=np.float64)
    finite = np.isfinite(xyz).all(axis=1)
    finite &= np.max(np.abs(xyz), axis=1) < INVALID_POSE_ABS
    return xyz[finite]


def _arm_motion(xyz: np.ndarray, dt: float) -> dict[str, Any]:
    empty: dict[str, Any] = {
        "path_length": 0.0,
        "displacement": 0.0,
        "speeds": np.zeros(0, dtype=np.float64),
        "n_valid": int(len(xyz)),
    }
    if len(xyz) < 2:
        empty["displacement"] = 0.0
        return empty
    deltas = np.diff(xyz, axis=0)
    step = np.linalg.norm(deltas, axis=1)
    speeds = step / max(dt, 1e-9)
    return {
        "path_length": float(step.sum()),
        "displacement": float(np.linalg.norm(xyz[-1] - xyz[0])),
        "speeds": speeds,
        "deltas": deltas,
        "n_valid": int(len(xyz)),
    }


def motion_features(
    left: np.ndarray | None,
    right: np.ndarray | None,
    *,
    n_frames: int,
    fps: float | None,
) -> dict[str, float]:
    dt = 1.0 / fps if fps and fps > 0 else 1.0
    duration_s = float(n_frames / fps) if fps and fps > 0 else float(n_frames)
    left_xyz = _xyz_trajectory(left)
    right_xyz = _xyz_trajectory(right)
    left_m = _arm_motion(left_xyz, dt)
    right_m = _arm_motion(right_xyz, dt)
    speeds = np.concatenate([left_m["speeds"], right_m["speeds"]])
    if speeds.size == 0:
        mean_speed = std_speed = max_speed = accel = 0.0
        dir_ratio = 0.0
        stationary = 1.0
    else:
        mean_speed = float(speeds.mean())
        std_speed = float(speeds.std())
        max_speed = float(speeds.max())
        accel = (
            float(np.mean(np.abs(np.diff(speeds)) / max(dt, 1e-9)))
            if speeds.size > 1
            else 0.0
        )
        dir_flags = []
        for arm in (left_m, right_m):
            deltas = arm.get("deltas")
            arm_speeds = arm["speeds"]
            if deltas is None or len(deltas) < 2:
                continue
            a, b = deltas[:-1], deltas[1:]
            na = np.linalg.norm(a, axis=1)
            nb = np.linalg.norm(b, axis=1)
            ok = (na > 1e-8) & (nb > 1e-8) & (arm_speeds[1:] > STATIONARY_SPEED_MPS)
            cos = np.ones(len(a))
            cos[ok] = np.clip((a[ok] * b[ok]).sum(axis=1) / (na[ok] * nb[ok]), -1.0, 1.0)
            ang = np.arccos(cos)
            dir_flags.append((ang > DIRECTION_CHANGE_RAD) & ok)
        dir_ratio = float(np.concatenate(dir_flags).mean()) if dir_flags else 0.0
        stationary = float((speeds < STATIONARY_SPEED_MPS).mean())
    return {
        "path_length": float(left_m["path_length"] + right_m["path_length"]),
        "displacement": float(
            np.mean([left_m["displacement"], right_m["displacement"]])
        ),
        "mean_speed": mean_speed,
        "speed_std": std_speed,
        "max_speed": max_speed,
        "mean_abs_accel": accel,
        "direction_change_ratio": dir_ratio,
        "stationary_ratio": stationary,
        "duration_s": duration_s,
        "n_frames": float(n_frames),
        "n_valid_left": float(left_m["n_valid"]),
        "n_valid_right": float(right_m["n_valid"]),
        "fps": float(fps) if fps and fps > 0 else 0.0,
    }


def quality_features(
    *,
    n_frames: int,
    n_sampled: int,
    n_decoded: int,
    motion: dict[str, float],
) -> dict[str, float]:
    valid_frame = float(n_decoded / n_sampled) if n_sampled else 0.0
    expected = max(float(n_frames), 1.0)
    completeness = float(
        min(motion["n_valid_left"], motion["n_valid_right"]) / expected
    )
    finite_ratio = float(
        (motion["n_valid_left"] + motion["n_valid_right"]) / (2.0 * expected)
    )
    nonstationary = float(1.0 - np.clip(motion["stationary_ratio"], 0.0, 1.0))
    temporal = 1.0 if (n_frames > 1 and motion["fps"] > 0) else 0.0
    score = (
        0.25 * valid_frame
        + 0.25 * np.clip(completeness, 0.0, 1.0)
        + 0.20 * np.clip(finite_ratio, 0.0, 1.0)
        + 0.15 * nonstationary
        + 0.15 * temporal
    )
    return {
        "quality_score": float(np.clip(score, 0.0, 1.0)),
        "quality_valid_frame_ratio": valid_frame,
        "quality_trajectory_completeness": float(np.clip(completeness, 0.0, 1.0)),
        "quality_finite_pose_ratio": float(np.clip(finite_ratio, 0.0, 1.0)),
        "quality_nonstationary": nonstationary,
        "quality_temporal_validity": temporal,
    }
