from __future__ import annotations

import math

import numpy as np


TWO_PI = 2.0 * math.pi


def compute_wrapped_phase_4step(
    i0: np.ndarray,
    i90: np.ndarray,
    i180: np.ndarray,
    i270: np.ndarray,
    convention: str = "default",
) -> np.ndarray:
    """Compute 4-step PSP wrapped phase in the range [-pi, pi]."""
    y_default = i0 - i180
    x_default = i270 - i90

    if convention == "default":
        wrapped = np.arctan2(y_default, x_default)
    elif convention == "negated":
        wrapped = -np.arctan2(y_default, x_default)
    elif convention == "swapped":
        wrapped = np.arctan2(x_default, y_default)
    else:
        raise ValueError(
            "phase_convention must be one of: default, negated, swapped"
        )

    return wrapped.astype(np.float32)


def wrapped_to_0_2pi(
    wrapped_phase: np.ndarray, boundary_epsilon: float = 1e-6
) -> np.ndarray:
    """Map wrapped phase to [0, 2pi), stabilizing the shared 0/2pi boundary."""
    phase = np.mod(wrapped_phase, TWO_PI).astype(np.float32)
    near_boundary = (phase <= boundary_epsilon) | ((TWO_PI - phase) <= boundary_epsilon)
    return np.where(near_boundary, 0.0, phase).astype(np.float32)


def diagnose_phase_conventions(
    i0: np.ndarray,
    i90: np.ndarray,
    i180: np.ndarray,
    i270: np.ndarray,
) -> dict[str, object]:
    """Score cosine-family convention fitness on the first and center rows.

    The cosine convention expects ``I0-I180 = cos(phi)`` and
    ``I270-I90 = sin(phi)``.  A normalized vector dot product gives a score
    in [-1, 1] without depending on albedo or modulation amplitude.
    """
    arrays = tuple(np.asarray(image, dtype=np.float32) for image in (i0, i90, i180, i270))
    if any(image.ndim != 2 for image in arrays):
        raise ValueError("phase convention diagnosis expects 2D sine images")
    rows = tuple(dict.fromkeys((0, arrays[0].shape[0] // 2)))
    in_phase = arrays[0] - arrays[2]
    quadrature = arrays[3] - arrays[1]
    magnitude = np.hypot(in_phase, quadrature)

    scores: dict[str, float | None] = {}
    row_scores: dict[str, dict[str, float | None]] = {}
    for convention in ("default", "negated", "swapped"):
        wrapped = compute_wrapped_phase_4step(*arrays, convention=convention)
        per_row: dict[str, float | None] = {}
        values: list[float] = []
        for row in rows:
            valid = np.isfinite(magnitude[row]) & (magnitude[row] > 1e-6)
            if not np.any(valid):
                score = None
            else:
                expected_cos = in_phase[row, valid] / magnitude[row, valid]
                expected_sin = quadrature[row, valid] / magnitude[row, valid]
                score = float(
                    np.mean(
                        np.cos(wrapped[row, valid]) * expected_cos
                        + np.sin(wrapped[row, valid]) * expected_sin
                    )
                )
                values.append(score)
            per_row[str(row)] = score
        row_scores[convention] = per_row
        scores[convention] = float(np.mean(values)) if values else None

    finite_scores = {key: value for key, value in scores.items() if value is not None}
    recommended = max(finite_scores, key=finite_scores.get) if finite_scores else None
    return {
        "method": "cosine_quadrature_first_and_center_rows",
        "sample_rows": list(rows),
        "scores": scores,
        "row_scores": row_scores,
        "recommended": recommended,
    }


def compute_modulation(
    i0: np.ndarray,
    i90: np.ndarray,
    i180: np.ndarray,
    i270: np.ndarray,
    epsilon: float = 1e-6,
) -> tuple[np.ndarray, np.ndarray]:
    """Return proportional and mean-normalized 4-step modulation."""
    quadrature = i270 - i90
    in_phase = i0 - i180
    modulation = 0.5 * np.sqrt(quadrature * quadrature + in_phase * in_phase)
    mean_intensity = (i0 + i90 + i180 + i270) / 4.0
    modulation_norm = modulation / np.maximum(mean_intensity, epsilon)
    return modulation.astype(np.float32), modulation_norm.astype(np.float32)
