"""Fit a central-workspace, position-dependent phase-to-mm calibration.

The input manifest describes known-height scans that were decoded against the
same flat-stage reference.  Each scan contributes its 0 and 180 degree delta
phase maps.  The fitted NPZ is directly usable as ``--calibration-config``
with ``--height-mode phase_linear``.

The calibration intentionally limits output to the common top-surface region
of the supplied reference pieces.  That is preferable to silently reporting
millimetres in an area with no known-height evidence.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np


@dataclass(frozen=True)
class Sample:
    height_mm: float
    processed_dir: Path
    roi_xyxy: tuple[int, int, int, int]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="Output .npz calibration")
    parser.add_argument("--report", type=Path, required=True, help="Output JSON fit report")
    parser.add_argument(
        "--rig-layout",
        choices=("camera_tilt_30_projector_vertical", "projector_tilt_30_camera_vertical"),
        default="camera_tilt_30_projector_vertical",
    )
    parser.add_argument("--camera-tilt-deg", type=float, default=30.0)
    parser.add_argument("--projector-tilt-deg", type=float, default=0.0)
    return parser


def _load_manifest(path: Path) -> tuple[str, list[Sample]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    samples: list[Sample] = []
    for item in payload.get("samples", []):
        roi = tuple(int(value) for value in item["roi_xyxy"])
        if len(roi) != 4 or roi[0] >= roi[2] or roi[1] >= roi[3]:
            raise ValueError(f"Invalid roi_xyxy in {item}")
        height = float(item["height_mm"])
        if not np.isfinite(height):
            raise ValueError(f"height_mm must be finite: {item}")
        samples.append(Sample(height, Path(item["processed_dir"]), roi))
    if len(samples) < 2:
        raise ValueError("At least two known-height samples are required")
    if len({sample.height_mm for sample in samples}) < 2:
        raise ValueError("Known-height samples must include at least two distinct heights")
    return str(payload.get("calibration_id", path.stem)), sorted(samples, key=lambda item: item.height_mm)


def _load_view(sample: Sample, view: int) -> tuple[np.ndarray, np.ndarray]:
    base = sample.processed_dir / "views" / f"deg_{view}"
    delta = np.load(base / "height" / "delta_phase.npy").astype(np.float32)
    mask_image = cv2.imread(str(base / "masks" / "combined_mask.png"), cv2.IMREAD_GRAYSCALE)
    if mask_image is None:
        raise FileNotFoundError(f"Missing combined mask: {base}")
    mask = (mask_image > 0) & np.isfinite(delta)
    return delta, mask


def _common_roi(samples: list[Sample], shape: tuple[int, int]) -> tuple[int, int, int, int]:
    x0 = max(sample.roi_xyxy[0] for sample in samples)
    y0 = max(sample.roi_xyxy[1] for sample in samples)
    x1 = min(sample.roi_xyxy[2] for sample in samples)
    y1 = min(sample.roi_xyxy[3] for sample in samples)
    height, width = shape
    if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
        raise ValueError("The known-height ROIs do not have a non-empty common area")
    return x0, y0, x1, y1


def _fit_view(
    samples: list[Sample],
    view: int,
    common_roi: tuple[int, int, int, int],
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    decoded = [_load_view(sample, view) for sample in samples]
    shape = decoded[0][0].shape
    if any(delta.shape != shape for delta, _mask in decoded):
        raise ValueError(f"View {view}: decoded scan shapes differ")
    x0, y0, x1, y1 = common_roi
    cropped = [(delta[y0:y1, x0:x1], mask[y0:y1, x0:x1]) for delta, mask in decoded]

    low_delta, low_mask = cropped[0]
    high_delta, high_mask = cropped[-1]
    joint = low_mask & high_mask
    if int(joint.sum()) < 100:
        raise ValueError(f"View {view}: fewer than 100 paired valid pixels in the common ROI")
    raw_change = high_delta[joint] - low_delta[joint]
    sign = -1.0 if float(np.median(raw_change)) < 0 else 1.0

    # Pair all height levels.  A paired-pixel phase difference is a direct local
    # slope observation and remains valid even when the reference piece was put
    # down a few pixels away from the nominal centre.
    slope_observations: list[np.ndarray] = []
    for index in range(len(cropped)):
        delta_a, mask_a = cropped[index]
        for other in range(index + 1, len(cropped)):
            delta_b, mask_b = cropped[other]
            paired = mask_a & mask_b
            if int(paired.sum()) < 100:
                continue
            height_span = samples[other].height_mm - samples[index].height_mm
            values = sign * (delta_b[paired] - delta_a[paired]) / height_span
            values = values[np.isfinite(values) & (values > 0)]
            if values.size:
                slope_observations.append(values)
    if not slope_observations:
        raise ValueError(f"View {view}: no positive paired phase/mm observations")
    phase_per_mm = float(np.median(np.concatenate(slope_observations)))

    roi_width = x1 - x0
    offset_by_column = np.full(roi_width, np.nan, dtype=np.float32)
    for column in range(roi_width):
        observations: list[np.ndarray] = []
        for sample, (delta, mask) in zip(samples, cropped):
            values = sign * delta[:, column][mask[:, column]] - phase_per_mm * sample.height_mm
            if values.size >= 4:
                observations.append(values)
        if observations:
            offset_by_column[column] = float(np.median(np.concatenate(observations)))
    finite_columns = np.flatnonzero(np.isfinite(offset_by_column))
    if finite_columns.size < 2:
        raise ValueError(f"View {view}: insufficient columns for a position-dependent offset")
    interpolated_offset = np.interp(
        np.arange(roi_width), finite_columns, offset_by_column[finite_columns]
    ).astype(np.float32)

    phase_map = np.full(shape, np.nan, dtype=np.float32)
    offset_map = np.full(shape, np.nan, dtype=np.float32)
    phase_map[y0:y1, x0:x1] = phase_per_mm
    offset_map[y0:y1, x0:x1] = interpolated_offset[None, :]

    sample_errors: list[dict[str, Any]] = []
    for sample, (delta, mask) in zip(samples, cropped):
        predicted = (sign * delta - interpolated_offset[None, :]) / phase_per_mm
        valid = mask & np.isfinite(predicted)
        error = predicted[valid] - sample.height_mm
        sample_errors.append(
            {
                "height_mm": sample.height_mm,
                "valid_pixel_count": int(error.size),
                "median_error_mm": float(np.median(error)),
                "mae_mm": float(np.mean(np.abs(error))),
                "rmse_mm": float(np.sqrt(np.mean(error * error))),
                "p95_absolute_error_mm": float(np.quantile(np.abs(error), 0.95)),
            }
        )

    return (
        {
            f"phase_linear_phase_per_mm_{view}": phase_map,
            f"phase_linear_offset_phase_{view}": offset_map,
            f"phase_linear_height_sign_{view}": np.array(sign, dtype=np.float32),
        },
        {
            "height_sign": sign,
            "phase_per_mm": phase_per_mm,
            "paired_slope_observation_count": int(sum(values.size for values in slope_observations)),
            "paired_slope_p10_p90": [
                float(np.quantile(np.concatenate(slope_observations), 0.10)),
                float(np.quantile(np.concatenate(slope_observations), 0.90)),
            ],
            "sample_fit": sample_errors,
        },
    )


def main() -> None:
    args = _parser().parse_args()
    calibration_id, samples = _load_manifest(args.manifest)
    first_delta, _first_mask = _load_view(samples[0], 0)
    roi = _common_roi(samples, first_delta.shape)
    arrays: dict[str, np.ndarray] = {}
    views: dict[str, Any] = {}
    for view in (0, 180):
        view_arrays, view_report = _fit_view(samples, view, roi)
        arrays.update(view_arrays)
        views[f"deg_{view}"] = view_report

    rig = {
        "layout": args.rig_layout,
        "camera_tilt_deg": float(args.camera_tilt_deg),
        "projector_tilt_deg": float(args.projector_tilt_deg),
    }
    if rig["layout"] == "camera_tilt_30_projector_vertical" and (
        rig["camera_tilt_deg"] != 30.0 or rig["projector_tilt_deg"] != 0.0
    ):
        raise ValueError("camera_tilt_30_projector_vertical requires camera=30 and projector=0")
    arrays.update(
        {
            "rig_layout": np.array(rig["layout"]),
            "camera_tilt_deg": np.array(rig["camera_tilt_deg"], dtype=np.float32),
            "projector_tilt_deg": np.array(rig["projector_tilt_deg"], dtype=np.float32),
            "calibration_id": np.array(calibration_id),
        }
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.output, **arrays)
    report = {
        "calibration_id": calibration_id,
        "method": "position_dependent_phase_linear_column_offset",
        "units": "mm",
        "rig": rig,
        "common_roi_xyxy": list(roi),
        "image_shape": list(first_delta.shape),
        "samples": [
            {
                "height_mm": sample.height_mm,
                "processed_dir": str(sample.processed_dir),
                "roi_xyxy": list(sample.roi_xyxy),
            }
            for sample in samples
        ],
        "views": views,
        "limitations": [
            "Fit errors are in-sample because only known-height references were supplied.",
            "Metric output is intentionally limited to the common ROI; add known-height samples to expand it.",
            "A separate known-height scan is required for an independent accuracy claim.",
        ],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved calibration: {args.output}")
    print(f"Saved report: {args.report}")


if __name__ == "__main__":
    main()
