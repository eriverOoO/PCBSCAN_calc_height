"""Persistent, validated flat-stage reference storage for the desktop GUI."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


MIN_VALID_RATIO = 0.15
MAX_P95_RESIDUAL_FRACTION = 0.01
MAX_OUTLIER_RATIO = 0.02
_HOMOGRAPHY_SAMPLE_SIZE = 8
_HOMOGRAPHY_RANSAC_TRIALS = 128


@dataclass(frozen=True)
class FlatnessReport:
    valid_ratio: float
    phase_span: float
    p95_plane_residual: float
    outlier_ratio: float
    valid: bool
    reason: str

    def as_dict(self) -> dict[str, float | bool | str]:
        return {
            "valid_ratio": self.valid_ratio,
            "phase_span": self.phase_span,
            "p95_plane_residual": self.p95_plane_residual,
            "outlier_ratio": self.outlier_ratio,
            "valid": self.valid,
            "reason": self.reason,
        }


def validate_flat_stage(phase: np.ndarray, mask: np.ndarray) -> FlatnessReport:
    """Check that a decoded reference is sufficiently covered and smooth.

    A flat physical stage does not in general create a linear phase image in
    camera coordinates: projector-to-camera perspective maps it through a
    homography.  Fit that projective baseline, then reject local departures
    such as a PCB or other object left on the stage.
    """
    phase = np.asarray(phase, dtype=np.float64)
    valid = np.asarray(mask, dtype=bool) & np.isfinite(phase)
    valid_ratio = float(valid.mean())
    if valid_ratio < MIN_VALID_RATIO:
        return FlatnessReport(valid_ratio, 0.0, float("inf"), 1.0, False, "valid coverage is too low")

    y, x = np.indices(phase.shape)
    values = phase[valid]
    span = float(np.quantile(values, 0.99) - np.quantile(values, 0.01))
    if span <= 1e-6:
        return FlatnessReport(valid_ratio, span, 0.0, 1.0, False, "phase span is too small")

    # Use the scan's phase span to remain independent of projector resolution.
    threshold = max(1e-6, span * MAX_P95_RESIDUAL_FRACTION)
    x_values = x[valid].astype(np.float64, copy=False)
    y_values = y[valid].astype(np.float64, copy=False)
    coefficients = _fit_projective_phase_baseline(
        x_values,
        y_values,
        values,
        threshold,
    )
    if coefficients is None:
        return FlatnessReport(
            valid_ratio,
            span,
            float("inf"),
            1.0,
            False,
            "could not fit a projective flat-stage baseline",
        )

    residual = values - _evaluate_projective_phase_baseline(coefficients, x_values, y_values)
    p95 = float(np.quantile(np.abs(residual), 0.95))
    outlier_ratio = float(np.mean(np.abs(residual) > threshold))
    if p95 > threshold or outlier_ratio > MAX_OUTLIER_RATIO:
        return FlatnessReport(
            valid_ratio,
            span,
            p95,
            outlier_ratio,
            False,
            "surface is not sufficiently planar; remove all objects from the stage",
        )
    return FlatnessReport(valid_ratio, span, p95, outlier_ratio, True, "flat stage accepted")


def _fit_projective_phase_baseline(
    x: np.ndarray,
    y: np.ndarray,
    values: np.ndarray,
    inlier_threshold: float,
) -> np.ndarray | None:
    """Fit phase=(ax+by+c)/(gx+hy+1), tolerating an object in the view."""
    count = values.size
    if count < _HOMOGRAPHY_SAMPLE_SIZE:
        return None

    candidates: list[np.ndarray] = []
    full_fit = _solve_projective_phase(x, y, values)
    if full_fit is not None:
        candidates.append(full_fit)

    rng = np.random.default_rng(0)
    for _ in range(_HOMOGRAPHY_RANSAC_TRIALS):
        sample = rng.choice(count, size=_HOMOGRAPHY_SAMPLE_SIZE, replace=False)
        fit = _solve_projective_phase(x[sample], y[sample], values[sample])
        if fit is not None:
            candidates.append(fit)

    best_fit: np.ndarray | None = None
    best_inlier_count = -1
    for fit in candidates:
        residual = np.abs(values - _evaluate_projective_phase_baseline(fit, x, y))
        inlier_count = int(np.count_nonzero(residual <= inlier_threshold))
        if inlier_count > best_inlier_count:
            best_fit = fit
            best_inlier_count = inlier_count

    if best_fit is None or best_inlier_count < _HOMOGRAPHY_SAMPLE_SIZE:
        return None

    residual = np.abs(values - _evaluate_projective_phase_baseline(best_fit, x, y))
    refined_fit = _solve_projective_phase(
        x[residual <= inlier_threshold],
        y[residual <= inlier_threshold],
        values[residual <= inlier_threshold],
    )
    return refined_fit if refined_fit is not None else best_fit


def _solve_projective_phase(
    x: np.ndarray,
    y: np.ndarray,
    values: np.ndarray,
) -> np.ndarray | None:
    """Solve the five normalized parameters of a one-coordinate homography."""
    design = np.column_stack((x, y, np.ones(values.size), -values * x, -values * y))
    coefficients, _, rank, _ = np.linalg.lstsq(design, values, rcond=None)
    if rank < 5 or not np.all(np.isfinite(coefficients)):
        return None
    return coefficients


def _evaluate_projective_phase_baseline(
    coefficients: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
) -> np.ndarray:
    numerator = coefficients[0] * x + coefficients[1] * y + coefficients[2]
    denominator = 1.0 + coefficients[3] * x + coefficients[4] * y
    with np.errstate(divide="ignore", invalid="ignore"):
        return numerator / denominator


def default_reference_store_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".pcb_fpp_decoder"))
    return base / "PCB_FPP_Decoder" / "flat_stage_reference"


class ReferenceStore:
    """Keeps the most recently accepted pair of 0/180-degree references."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else default_reference_store_dir()

    @property
    def phase_0_path(self) -> Path:
        return self.root / "reference_phase_0.npy"

    @property
    def phase_180_path(self) -> Path:
        return self.root / "reference_phase_180.npy"

    @property
    def metadata_path(self) -> Path:
        return self.root / "reference_metadata.json"

    def is_available(self) -> bool:
        return self.phase_0_path.is_file() and self.phase_180_path.is_file() and self.metadata_path.is_file()

    def metadata(self) -> dict[str, object] | None:
        if not self.is_available():
            return None
        try:
            return json.loads(self.metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def save(
        self,
        phase_0: np.ndarray,
        phase_180: np.ndarray,
        report_0: FlatnessReport,
        report_180: FlatnessReport,
        source_0: Path,
        source_180: Path,
    ) -> None:
        if not report_0.valid or not report_180.valid:
            raise ValueError("only validated flat-stage references can be stored")
        self.root.mkdir(parents=True, exist_ok=True)
        for target, phase in ((self.phase_0_path, phase_0), (self.phase_180_path, phase_180)):
            temporary = target.with_suffix(".tmp")
            with temporary.open("wb") as handle:
                np.save(handle, np.asarray(phase, dtype=np.float32))
            temporary.replace(target)
        metadata = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_0": str(Path(source_0).resolve()),
            "source_180": str(Path(source_180).resolve()),
            "flatness_0": report_0.as_dict(),
            "flatness_180": report_180.as_dict(),
        }
        self.metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
