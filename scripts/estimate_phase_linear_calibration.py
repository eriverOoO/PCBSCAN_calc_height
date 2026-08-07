"""Fit a marker-aligned, position-dependent phase-to-mm calibration.

Known-height pieces are automatically located from their ArUco prescan image.
The manifest deliberately contains no pixel ROI: the flat 0-mm scan provides
the stage reference and each non-zero scan contributes only its detected top
surface.  Pixels outside the actually observed calibration surfaces remain
invalid rather than being assigned an invented millimetre scale.
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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="Output .npz calibration")
    parser.add_argument("--report", type=Path, required=True, help="Output JSON fit report")
    return parser


def _load_manifest(path: Path) -> tuple[str, float | None, list[Sample]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    samples: list[Sample] = []
    for item in payload.get("samples", []):
        height = float(item["height_mm"])
        if not np.isfinite(height):
            raise ValueError(f"height_mm must be finite: {item}")
        samples.append(Sample(height, Path(item["processed_dir"])))
    if len(samples) < 2:
        raise ValueError("At least two known-height samples are required")
    if not any(sample.height_mm == 0.0 for sample in samples):
        raise ValueError("A 0-mm flat-stage scan is required for marker-aligned calibration")
    if len({sample.height_mm for sample in samples}) < 2:
        raise ValueError("Known-height samples must include at least two distinct heights")
    configured_sign = payload.get("height_sign")
    if configured_sign is not None:
        configured_sign = float(configured_sign)
        if configured_sign not in (-1.0, 1.0):
            raise ValueError("height_sign must be -1 or 1 when supplied")
    return str(payload.get("calibration_id", path.stem)), configured_sign, sorted(samples, key=lambda item: item.height_mm)


def _load_view(sample: Sample, view: int) -> tuple[np.ndarray, np.ndarray]:
    base = sample.processed_dir / "views" / f"deg_{view}"
    delta = np.load(base / "height" / "delta_phase.npy").astype(np.float32)
    mask_image = cv2.imread(str(base / "masks" / "combined_mask.png"), cv2.IMREAD_GRAYSCALE)
    if mask_image is None:
        raise FileNotFoundError(f"Missing combined mask: {base}")
    return delta, (mask_image > 0) & np.isfinite(delta)


def _capture_dir(sample: Sample) -> Path:
    report_path = sample.processed_dir / "decode_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return Path(report["input_dir"]).parent


def _stage_center_from_markers(image: np.ndarray) -> tuple[float, float]:
    """Return the marker-defined stage centre, falling back to image centre."""
    fallback = (image.shape[1] / 2.0, image.shape[0] / 2.0)
    if not hasattr(cv2, "aruco"):
        return fallback
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    detector = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())
    corners, ids, _rejected = detector.detectMarkers(image)
    if ids is None or len(corners) < 2:
        return fallback
    centres = np.asarray([corner.reshape(-1, 2).mean(axis=0) for corner in corners], dtype=np.float32)
    return tuple(np.median(centres, axis=0).tolist())


def _detect_top_surface(sample: Sample, view: int, shape: tuple[int, int]) -> tuple[np.ndarray, dict[str, Any]]:
    """Detect the central raised piece without a user-supplied pixel ROI.

    The detector uses a low-frequency illumination estimate, then selects the
    connected dark object closest to the ArUco-defined stage centre.  Marker
    components are far from this centre and are therefore not selected.
    """
    filename = "prescan_0.png" if view == 0 else "prescan_nominal_180.png"
    image_path = _capture_dir(sample) / "aruco_prescan" / filename
    image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise FileNotFoundError(f"Missing ArUco prescan: {image_path}")
    if image.shape != shape:
        raise ValueError(f"Prescan shape does not match decoded scan: {image_path}")

    background = cv2.GaussianBlur(image, (0, 0), 70.0)
    darkness = cv2.subtract(background, image)
    binary = (darkness > 10).astype(np.uint8)
    binary = cv2.morphologyEx(
        binary, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25))
    )
    binary = cv2.morphologyEx(
        binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    )
    count, labels, stats, _centres = cv2.connectedComponentsWithStats(binary, connectivity=8)
    stage_cx, stage_cy = _stage_center_from_markers(image)
    best: tuple[float, int, np.ndarray] | None = None
    for label in range(1, count):
        x, y, width, height, area = stats[label]
        if int(area) < 2_000:
            continue
        cx, cy = x + width / 2.0, y + height / 2.0
        # Prefer the marker-centred candidate, while retaining support for a
        # hand-placed piece that is not exactly at the geometric centre.
        score = float(np.hypot(cx - stage_cx, cy - stage_cy) / np.sqrt(area))
        if best is None or score < best[0]:
            best = (score, label, stats[label])
    if best is None:
        raise ValueError(f"Could not automatically detect a raised top surface in {image_path}")

    top_surface = labels == best[1]
    top_surface = cv2.erode(
        top_surface.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21))
    ).astype(bool)
    x, y, width, height, area = (int(value) for value in best[2])
    return top_surface, {
        "mode": "aruco_prescan_auto_surface",
        "prescan": str(image_path),
        "stage_center_xy": [stage_cx, stage_cy],
        "bounding_box_xywh": [x, y, width, height],
        "detected_area_px": area,
        "eroded_area_px": int(top_surface.sum()),
    }


def _fit_view(
    samples: list[Sample],
    view: int,
    configured_sign: float | None,
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    decoded = {sample: _load_view(sample, view) for sample in samples}
    reference = next(sample for sample in samples if sample.height_mm == 0.0)
    reference_delta, reference_mask = decoded[reference]
    shape = reference_delta.shape
    if any(delta.shape != shape for delta, _mask in decoded.values()):
        raise ValueError(f"View {view}: decoded scan shapes differ")

    surfaces: dict[Sample, np.ndarray] = {}
    surface_reports: dict[Sample, dict[str, Any]] = {}
    for sample in samples:
        if sample.height_mm == 0.0:
            continue
        surface, report = _detect_top_surface(sample, view, shape)
        surfaces[sample] = surface
        surface_reports[sample] = report

    # The sign is stable for a projector/camera configuration.  Existing
    # profiles may pin it in the manifest; otherwise use the aggregate median
    # change over the automatically selected surfaces.
    if configured_sign is not None:
        sign = configured_sign
    else:
        signed_medians = []
        for sample, surface in surfaces.items():
            delta, mask = decoded[sample]
            values = (delta - reference_delta)[surface & mask & reference_mask]
            if values.size:
                signed_medians.append(float(np.median(values)))
        sign = -1.0 if float(np.median(signed_medians)) < 0 else 1.0

    phase_observations: list[np.ndarray] = []
    sample_observations: dict[Sample, np.ndarray] = {}
    skipped_samples: dict[Sample, str] = {}
    for sample, surface in surfaces.items():
        delta, mask = decoded[sample]
        valid = surface & mask & reference_mask
        values = sign * (delta[valid] - reference_delta[valid]) / sample.height_mm
        values = values[np.isfinite(values) & (values > 0)]
        if values.size < 100:
            skipped_samples[sample] = "fewer than 100 usable top-surface observations"
            continue
        phase_observations.append(values)
        sample_observations[sample] = values
    if not phase_observations:
        raise ValueError(f"View {view}: no known-height top surface has enough usable observations")
    all_phase = np.concatenate(phase_observations)
    phase_per_mm = float(np.median(all_phase))
    lower, upper = np.quantile(all_phase, [0.10, 0.90])
    if not np.isfinite(phase_per_mm) or phase_per_mm <= 0:
        raise ValueError(f"View {view}: no positive phase/mm observations")

    # Each known top surface contributes a local phase/mm estimate.  Taking a
    # per-pixel median retains position dependence without assuming that every
    # hand-placed piece covers the same rectangle.
    phase_map = np.full(shape, np.nan, dtype=np.float32)
    count_map = np.zeros(shape, dtype=np.uint16)
    values_by_pixel: dict[tuple[int, int], list[float]] = {}
    for sample, surface in surfaces.items():
        if sample not in sample_observations:
            continue
        delta, mask = decoded[sample]
        valid = surface & mask & reference_mask
        local = sign * (delta - reference_delta) / sample.height_mm
        valid &= np.isfinite(local) & (local >= lower) & (local <= upper)
        ys, xs = np.nonzero(valid)
        for y, x in zip(ys.tolist(), xs.tolist()):
            values_by_pixel.setdefault((y, x), []).append(float(local[y, x]))
    for (y, x), values in values_by_pixel.items():
        phase_map[y, x] = float(np.median(values))
        count_map[y, x] = len(values)

    # A 0-mm reference supplies the local intercept everywhere it is valid;
    # the metric output is restricted further by phase_map coverage.
    offset_map = np.full(shape, np.nan, dtype=np.float32)
    offset_map[reference_mask] = sign * reference_delta[reference_mask]

    sample_fit: list[dict[str, Any]] = []
    for sample, surface in surfaces.items():
        if sample not in sample_observations:
            sample_fit.append(
                {
                    "height_mm": sample.height_mm,
                    "valid_pixel_count": 0,
                    "excluded": True,
                    "reason": skipped_samples[sample],
                    "surface": surface_reports[sample],
                }
            )
            continue
        delta, mask = decoded[sample]
        valid = surface & mask & np.isfinite(phase_map) & np.isfinite(offset_map)
        predicted = (sign * delta[valid] - offset_map[valid]) / phase_map[valid]
        error = predicted - sample.height_mm
        sample_fit.append(
            {
                "height_mm": sample.height_mm,
                "valid_pixel_count": int(error.size),
                "median_error_mm": float(np.median(error)) if error.size else None,
                "mae_mm": float(np.mean(np.abs(error))) if error.size else None,
                "rmse_mm": float(np.sqrt(np.mean(error * error))) if error.size else None,
                "p95_absolute_error_mm": float(np.quantile(np.abs(error), 0.95)) if error.size else None,
                "surface": surface_reports[sample],
                "phase_per_mm_median": float(np.median(sample_observations[sample])),
                "phase_per_mm_p10_p90": [
                    float(np.quantile(sample_observations[sample], 0.10)),
                    float(np.quantile(sample_observations[sample], 0.90)),
                ],
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
            "global_phase_per_mm_median": phase_per_mm,
            "global_phase_per_mm_p10_p90": [float(lower), float(upper)],
            "calibrated_pixel_count": int(np.isfinite(phase_map).sum()),
            "excluded_samples": [
                {"height_mm": sample.height_mm, "reason": reason}
                for sample, reason in skipped_samples.items()
            ],
            "sample_fit": sample_fit,
        },
    )


def main() -> None:
    args = _parser().parse_args()
    calibration_id, configured_sign, samples = _load_manifest(args.manifest)
    arrays: dict[str, np.ndarray] = {}
    views: dict[str, Any] = {}
    first_delta, _first_mask = _load_view(samples[0], 0)
    for view in (0, 180):
        view_arrays, view_report = _fit_view(samples, view, configured_sign)
        arrays.update(view_arrays)
        views[f"deg_{view}"] = view_report

    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.output, **arrays)
    report = {
        "calibration_id": calibration_id,
        "method": "aruco_prescan_auto_surface_local_phase_linear",
        "units": "mm",
        "image_shape": list(first_delta.shape),
        "samples": [
            {"height_mm": sample.height_mm, "processed_dir": str(sample.processed_dir)}
            for sample in samples
        ],
        "views": views,
        "limitations": [
            "No user-specified pixel ROI is used; surfaces are detected from ArUco prescans.",
            "Metric output is available only where a known-height top surface supplied phase evidence.",
            "A separate known-height scan is required for an independent accuracy claim.",
        ],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved calibration: {args.output}")
    print(f"Saved report: {args.report}")


if __name__ == "__main__":
    main()
