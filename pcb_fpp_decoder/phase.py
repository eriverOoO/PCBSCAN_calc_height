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


def wrapped_to_0_2pi(wrapped_phase: np.ndarray) -> np.ndarray:
    """Map wrapped phase from [-pi, pi] to [0, 2pi)."""
    return np.mod(wrapped_phase, TWO_PI).astype(np.float32)


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
