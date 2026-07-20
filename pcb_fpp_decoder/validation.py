from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from .decoder import FusionResult
from .visualization import save_colormap, save_mask


def accuracy_metrics(
    estimate: np.ndarray,
    ground_truth: np.ndarray,
    region_mask: np.ndarray,
) -> dict[str, float | int | None]:
    region = np.asarray(region_mask, dtype=bool)
    valid = region & np.isfinite(estimate) & np.isfinite(ground_truth)
    count = int(np.count_nonzero(region))
    valid_count = int(np.count_nonzero(valid))
    report: dict[str, float | int | None] = {
        "pixel_count": count,
        "valid_pixel_count": valid_count,
        "valid_ratio": float(valid_count / count) if count else None,
    }
    if not valid_count:
        report.update(
            {
                "bias_mm": None,
                "mae_mm": None,
                "rmse_mm": None,
                "median_absolute_error_mm": None,
                "p95_absolute_error_mm": None,
                "max_absolute_error_mm": None,
            }
        )
        return report

    error = np.asarray(estimate, dtype=np.float32)[valid] - np.asarray(
        ground_truth, dtype=np.float32
    )[valid]
    absolute = np.abs(error)
    report.update(
        {
            "bias_mm": float(np.mean(error)),
            "mae_mm": float(np.mean(absolute)),
            "rmse_mm": float(np.sqrt(np.mean(error * error))),
            "median_absolute_error_mm": float(np.median(absolute)),
            "p95_absolute_error_mm": float(np.percentile(absolute, 95)),
            "max_absolute_error_mm": float(np.max(absolute)),
        }
    )
    return report


def write_synthetic_validation_outputs(
    fusion: FusionResult,
    output_dir: Path,
    ground_truth: np.ndarray,
    pcb_mask: np.ndarray,
    *,
    manifests: dict[str, Any] | None = None,
    ground_truth_180_aligned: np.ndarray | None = None,
) -> dict[str, Any]:
    """Evaluate a completed decode; ground truth is never part of DecodeConfig."""
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    height = np.asarray(fusion.height.height, dtype=np.float32)
    gt = np.asarray(ground_truth, dtype=np.float32)
    pcb = np.asarray(pcb_mask, dtype=bool)
    if height.shape != gt.shape or height.shape != pcb.shape:
        raise ValueError("height, ground truth, and PCB mask shapes must match")

    valid = fusion.height.mask & np.isfinite(height)
    error = np.where(pcb & valid, height - gt, np.nan).astype(np.float32)
    np.save(output_dir / "height_mm.npy", height)
    np.save(output_dir / "error_mm.npy", error)
    save_colormap(
        output_dir / "height_mm.png",
        height,
        valid,
        cmap="turbo",
        with_colorbar=True,
        title="Fused metric height (mm)",
        colorbar_label="mm",
    )
    save_colormap(
        output_dir / "error_mm.png",
        error,
        pcb & valid,
        cmap="coolwarm",
        with_colorbar=True,
        title="Height error (mm)",
        colorbar_label="mm",
    )
    save_mask(output_dir / "cycle_slip_mask.png", fusion.cycle_slip_mask)
    save_mask(output_dir / "fusion_rejection_mask.png", fusion.fusion_rejection_mask)
    _save_overview(fusion, error, pcb & valid, output_dir / "overview_0_180_fused.png")

    regions = {
        "overall_pcb": pcb,
        "flat_substrate": pcb & (gt <= 0.05),
        "components": pcb & (gt > 0.05),
        "components_ge_1mm": pcb & (gt >= 1.0),
    }
    ground_truth_consistency: dict[str, Any] | None = None
    if ground_truth_180_aligned is not None:
        gt180 = np.asarray(ground_truth_180_aligned, dtype=np.float32)
        if gt180.shape != gt.shape:
            raise ValueError("aligned 180-degree ground truth shape does not match 0-degree truth")
        difference = np.abs(gt180 - gt)
        ground_truth_consistency = {
            "max_absolute_difference_mm": float(np.nanmax(difference)),
            "mean_absolute_difference_mm": float(np.nanmean(difference)),
        }
    report = {
        "schema_version": 1,
        "metric": True,
        "units": "mm",
        "ground_truth_usage": "post-decode accuracy evaluation only",
        "regions": {
            name: accuracy_metrics(height, gt, mask) for name, mask in regions.items()
        },
        "phase_height_regression": _phase_height_regression(fusion, gt, pcb),
        "ground_truth_0_180_consistency": ground_truth_consistency,
        "fusion": fusion.report.get("fusion", {}),
        "phase_diagnostics": {
            "deg_0": fusion.deg0.phase.convention_diagnostics,
            "deg_180": fusion.deg180.phase.convention_diagnostics,
        },
        "thresholds": {
            "min_signal": fusion.deg0.report["thresholds"]["min_signal"],
            "min_signal_mode": "manual",
            "selection_reason": "synthetic validation preset from calibration JSON",
            "deg_0_valid_ratio": fusion.deg0.report["mask_coverage"][
                "combined_mask_ratio"
            ],
            "deg_180_valid_ratio": fusion.deg180.report["mask_coverage"][
                "combined_mask_ratio"
            ],
        },
        "manifests": manifests or {},
    }
    (output_dir / "accuracy_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return report


def _phase_height_regression(
    fusion: FusionResult,
    ground_truth: np.ndarray,
    pcb_mask: np.ndarray,
) -> dict[str, float | None]:
    delta = fusion.deg0.height.delta_phase
    parameters = fusion.deg0.height.calibration_parameters
    if delta is None or "height_sign" not in parameters:
        return {"correlation": None, "slope_phase_per_mm": None, "offset_phase": None}
    signed = float(parameters["height_sign"]) * np.asarray(delta, dtype=np.float32)
    valid = pcb_mask & np.isfinite(signed) & np.isfinite(ground_truth)
    if np.count_nonzero(valid) < 2:
        return {"correlation": None, "slope_phase_per_mm": None, "offset_phase": None}
    x = np.asarray(ground_truth, dtype=np.float64)[valid]
    y = np.asarray(signed, dtype=np.float64)[valid]
    slope, offset = np.polyfit(x, y, 1)
    correlation = np.corrcoef(x, y)[0, 1]
    return {
        "correlation": float(correlation),
        "slope_phase_per_mm": float(slope),
        "offset_phase": float(offset),
    }


def manifest_summary(path: Path) -> dict[str, Any]:
    path = Path(path).expanduser().resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    frames = data.get("frames", [])
    return {
        "path": str(path),
        "scene_type": data.get("scene_type", "object"),
        "bit_depth": data.get("bit_depth"),
        "camera": data.get("camera"),
        "projector": data.get("projector"),
        "angles": data.get("angles"),
        "frame_count": len(frames),
        "frame_mapping": [
            {
                "angle_deg": frame.get("angle_deg"),
                "pattern_index": frame.get("pattern_index"),
                "label": frame.get("label"),
                "source_pattern": frame.get("source_pattern"),
                "inverse": frame.get("inverse"),
                "filename": frame.get("filename"),
                "dtype": frame.get("dtype"),
                "shape": frame.get("shape"),
            }
            for frame in frames
            if isinstance(frame, dict)
        ],
    }


def _save_overview(
    fusion: FusionResult,
    error: np.ndarray,
    error_mask: np.ndarray,
    path: Path,
) -> None:
    try:
        from .visualization import _pyplot_or_none

        plt = _pyplot_or_none()
    except Exception:
        plt = None
    if plt is None:
        save_colormap(path, fusion.height.height, fusion.height.mask, cmap="turbo")
        return

    arrays = (
        fusion.deg0.height.height,
        fusion.aligned_height_180,
        fusion.height.height,
        error,
    )
    masks = (
        fusion.deg0.height.mask,
        fusion.aligned_mask_180,
        fusion.height.mask,
        error_mask,
    )
    titles = ("0 degree (mm)", "180 degree aligned (mm)", "Fused (mm)", "Error (mm)")
    cmaps = ("turbo", "turbo", "turbo", "coolwarm")
    fig, axes = plt.subplots(2, 2, figsize=(12, 7), dpi=150)
    for ax, array, mask, title, cmap in zip(axes.flat, arrays, masks, titles, cmaps):
        display = np.where(mask, array, np.nan)
        image = ax.imshow(display, cmap=cmap)
        ax.set_title(title)
        ax.axis("off")
        fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
