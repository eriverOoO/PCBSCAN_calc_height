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
    """Check that a decoded reference is a sufficiently covered, smooth plane.

    Absolute structured-light phase normally has a large linear ramp.  We fit
    and remove that ramp, then reject a reference with broad local departures
    such as a PCB or other object left on the stage.
    """
    phase = np.asarray(phase, dtype=np.float64)
    valid = np.asarray(mask, dtype=bool) & np.isfinite(phase)
    valid_ratio = float(valid.mean())
    if valid_ratio < MIN_VALID_RATIO:
        return FlatnessReport(valid_ratio, 0.0, float("inf"), 1.0, False, "valid coverage is too low")

    y, x = np.indices(phase.shape)
    values = phase[valid]
    design = np.column_stack((x[valid], y[valid], np.ones(values.size)))
    coefficients, *_ = np.linalg.lstsq(design, values, rcond=None)
    residual = values - design @ coefficients
    span = float(np.quantile(values, 0.99) - np.quantile(values, 0.01))
    p95 = float(np.quantile(np.abs(residual), 0.95))
    # Use the scan's phase span to remain independent of projector resolution.
    threshold = max(1e-6, span * MAX_P95_RESIDUAL_FRACTION)
    outlier_ratio = float(np.mean(np.abs(residual) > threshold))
    if span <= 1e-6:
        return FlatnessReport(valid_ratio, span, p95, outlier_ratio, False, "phase span is too small")
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
