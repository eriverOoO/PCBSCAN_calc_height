"""Persistent, validated zero-plane reference surfaces.

The stored phase is deliberately separate from a scan output directory: capture
folders may be cleaned up, while a verified zero plane remains reusable.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class ReferenceSurfaceValidation:
    valid: bool
    valid_ratio: float
    residual_rms_phase: float
    residual_peak_to_valley_phase: float
    min_valid_ratio: float
    max_residual_rms_phase: float
    max_residual_peak_to_valley_phase: float


def validate_reference_surface(
    phase: np.ndarray,
    mask: np.ndarray,
    *,
    min_valid_ratio: float = 0.80,
    max_residual_rms_phase: float = 0.25,
    max_residual_peak_to_valley_phase: float = 1.00,
) -> ReferenceSurfaceValidation:
    """Check coverage and flatness after removing the best-fit phase plane.

    Removing the plane preserves the physical-flatness test while not rejecting
    the normal phase ramp caused by projector/camera geometry.  The unmodified
    phase is saved and later subtracted, so keystone cancellation is retained.
    """
    if not (0.0 < min_valid_ratio <= 1.0):
        raise ValueError("reference minimum valid ratio must be in (0, 1]")
    if max_residual_rms_phase <= 0 or max_residual_peak_to_valley_phase <= 0:
        raise ValueError("reference flatness thresholds must be positive")

    values = np.asarray(phase, dtype=np.float64)
    valid = np.asarray(mask, dtype=bool) & np.isfinite(values)
    valid_ratio = float(np.mean(valid))
    if valid.sum() < 3:
        rms = float("inf")
        peak_to_valley = float("inf")
    else:
        rows, cols = np.indices(values.shape, dtype=np.float64)
        design = np.column_stack((cols[valid], rows[valid], np.ones(valid.sum())))
        coefficients, *_ = np.linalg.lstsq(design, values[valid], rcond=None)
        residual = values[valid] - design @ coefficients
        rms = float(np.sqrt(np.mean(residual**2)))
        peak_to_valley = float(np.max(residual) - np.min(residual))

    accepted = (
        valid_ratio >= min_valid_ratio
        and rms <= max_residual_rms_phase
        and peak_to_valley <= max_residual_peak_to_valley_phase
    )
    return ReferenceSurfaceValidation(
        valid=accepted,
        valid_ratio=valid_ratio,
        residual_rms_phase=rms,
        residual_peak_to_valley_phase=peak_to_valley,
        min_valid_ratio=min_valid_ratio,
        max_residual_rms_phase=max_residual_rms_phase,
        max_residual_peak_to_valley_phase=max_residual_peak_to_valley_phase,
    )


def reference_phase_path(store: Path, view_angle: int | None) -> Path:
    angle = 0 if view_angle is None else int(view_angle)
    return Path(store) / f"angle_{angle:03d}" / "absolute_phase.npy"


def store_validated_reference_surface(
    store: Path,
    phase: np.ndarray,
    mask: np.ndarray,
    validation: ReferenceSurfaceValidation,
    *,
    view_angle: int | None,
    source_scan: Path,
) -> Path:
    if not validation.valid:
        raise ValueError("cannot store a reference surface that did not pass validation")
    phase_path = reference_phase_path(store, view_angle)
    phase_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(phase_path, np.asarray(phase, dtype=np.float32))
    np.save(phase_path.with_name("valid_mask.npy"), np.asarray(mask, dtype=bool))
    metadata = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_scan": str(Path(source_scan).resolve()),
        "view_angle": 0 if view_angle is None else int(view_angle),
        "phase_shape": list(np.asarray(phase).shape),
        "validation": asdict(validation),
    }
    phase_path.with_name("validation.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return phase_path
