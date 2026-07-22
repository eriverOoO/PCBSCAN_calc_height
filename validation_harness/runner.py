from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from pcb_fpp_decoder.decoder import (
    DecodeConfig,
    PcbFppDecoder,
    _fuse_height_maps,
    _height_confidence,
    _warp_float_with_mask,
)

from .metrics import detection_statistics, evaluate_regions
from .regions import build_region_masks
from .reports import failure_record, write_failures, write_overview, write_summary


def _read_mask(path: Path, shape: tuple[int, int]) -> np.ndarray:
    if not path.exists():
        return np.zeros(shape, dtype=bool)
    with Image.open(path) as image:
        mask = np.asarray(image) > 0
    if mask.shape != shape:
        raise ValueError(f"mask shape mismatch: {path}")
    return mask


def _load_gt_array(gt_dir: Path, stem: str) -> np.ndarray | None:
    """Evaluation-only GT reader. Never call this before decoding completes."""
    npy_path = gt_dir / f"{stem}.npy"
    if npy_path.exists():
        return np.load(npy_path, allow_pickle=False)
    for suffix in (".png", ".tif", ".tiff"):
        path = gt_dir / f"{stem}{suffix}"
        if path.exists():
            with Image.open(path) as image:
                return np.asarray(image)
    return None


def _load_view_gt_array(
    gt_dir: Path,
    view_name: str,
    stem: str,
    legacy_stem: str | None = None,
) -> np.ndarray | None:
    view_value = _load_gt_array(gt_dir / view_name, stem)
    if view_value is not None:
        return view_value
    return _load_gt_array(gt_dir, legacy_stem or stem)


class ValidationRunner:
    """Run production decode first, then evaluate outputs against isolated GT."""

    def __init__(self, config: DecodeConfig | None = None):
        # Use production defaults; validation does not override thresholds, phase
        # convention, height sign, filtering, or fusion policy.
        self.config = config or DecodeConfig(output_profile="compact")

    def run_case(self, case_root: str | Path, output_root: str | Path) -> dict[str, Any]:
        case = Path(case_root).expanduser().resolve()
        output = Path(output_root).expanduser().resolve()
        manifest_path = case / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        failures: list[dict[str, Any]] = []
        views = case / "views"

        try:
            # Decode/calibration inference stage: no GT files are opened here.
            reference_0 = PcbFppDecoder(self.config).decode(
                views / "reference_0", output / "decode" / "reference_0"
            )
            reference_180 = PcbFppDecoder(self.config).decode(
                views / "reference_180", output / "decode" / "reference_180"
            )
            requested_metric_mode = self.config.height_mode in {"triangulation", "inverse-linear"}
            height_mode = self.config.height_mode if requested_metric_mode else "reference"
            config_0 = replace(
                self.config,
                height_mode=height_mode,
                reference_phase=output / "decode" / "reference_0" / "phase" / "absolute_phase.npy",
            )
            config_180 = replace(
                self.config,
                height_mode=height_mode,
                reference_phase=output / "decode" / "reference_180" / "phase" / "absolute_phase.npy",
            )
            decoded_0 = PcbFppDecoder(config_0).decode(
                views / "object_0", output / "decode" / "object_0"
            )
            decoded_180 = PcbFppDecoder(config_180).decode(
                views / "object_180", output / "decode" / "object_180"
            )
            fusion_config = replace(
                self.config,
                height_mode="relative",
                reference_phase=None,
                reference_scan=None,
            )
            fused = PcbFppDecoder(fusion_config).decode_fused(
                views / "object_0", views / "object_180", output / "decode" / "fused"
            )
        except Exception as exc:
            failures.append(
                failure_record(
                    case_id=case.name,
                    seed=manifest.get("seed"),
                    profile=manifest.get("profile", {}).get("profile"),
                    reason=f"decode exception: {type(exc).__name__}: {exc}",
                    rerun_command=(
                        f'python tools/run_accuracy_matrix.py --dataset-root "{case}" '
                        f'--output-root "{output}"'
                    ),
                    impairment_manifest=manifest.get("views", {}),
                )
            )
            write_failures(output, failures)
            known = output / "known_failures"
            known.mkdir(parents=True, exist_ok=True)
            write_failures(known / case.name, failures)
            raise

        # Evaluation stage starts here; GT cannot influence any decode above.
        gt_dir = case / "gt"
        phase_gt_0 = _load_view_gt_array(
            gt_dir, "object_0", "absolute_phase_rad", "phase"
        )
        phase_gt_180 = _load_view_gt_array(
            gt_dir, "object_180", "absolute_phase_rad", "phase"
        )
        height_gt_0 = _load_view_gt_array(gt_dir, "object_0", "height_mm")
        height_gt_180 = _load_view_gt_array(gt_dir, "object_180", "height_mm")
        material_id_0 = _load_view_gt_array(gt_dir, "object_0", "material_id")
        material_id_180 = _load_view_gt_array(gt_dir, "object_180", "material_id")
        object_mask_0 = _load_view_gt_array(gt_dir, "object_0", "object_mask")
        object_mask_180 = _load_view_gt_array(gt_dir, "object_180", "object_mask")
        shape = decoded_0.absolute.absolute_phase.shape
        impairment_names = (
            "saturation",
            "shadow",
            "gray_boundary",
            "hot_pixel",
            "bit_flip",
            "cycle_slip",
            "registration_error",
        )
        impairment_masks_0 = {
            name: _read_mask(case / "masks" / "object_0" / f"{name}.png", shape)
            for name in impairment_names
        }
        impairment_masks_180 = {
            name: _read_mask(case / "masks" / "object_180" / f"{name}.png", shape)
            for name in impairment_names
        }
        regions_0 = build_region_masks(
            shape,
            object_mask=object_mask_0,
            material_id=material_id_0,
            height_gt=height_gt_0,
            impairment_masks=impairment_masks_0,
            view_valid_masks=(decoded_0.height.mask, decoded_180.height.mask),
        )
        regions_180 = build_region_masks(
            shape,
            object_mask=object_mask_180,
            material_id=material_id_180,
            height_gt=height_gt_180,
            impairment_masks=impairment_masks_180,
            view_valid_masks=(decoded_0.height.mask, decoded_180.height.mask),
        )
        fused_metric_height: np.ndarray | None = None
        fused_metric_mask: np.ndarray | None = None
        if decoded_0.height.metric and decoded_180.height.metric:
            confidence_0 = _height_confidence(decoded_0)
            confidence_180 = _height_confidence(decoded_180)
            aligned_height_180, aligned_mask_180 = _warp_float_with_mask(
                decoded_180.height.height,
                decoded_180.height.mask,
                shape,
                fused.transform_matrix,
                fused.transform_kind,
            )
            aligned_confidence_180, aligned_confidence_mask = _warp_float_with_mask(
                confidence_180,
                decoded_180.height.mask,
                shape,
                fused.transform_matrix,
                fused.transform_kind,
            )
            aligned_confidence_180 = np.where(
                aligned_confidence_mask, aligned_confidence_180, 0.0
            ).astype(np.float32)
            fused_metric_height, fused_metric_mask, _source, _confidence = _fuse_height_maps(
                decoded_0.height.height,
                decoded_0.height.mask,
                confidence_0,
                aligned_height_180,
                aligned_mask_180,
                aligned_confidence_180,
                self.config.fusion_mode,
                self.config.epsilon,
            )
            evaluation_dir = output / "evaluation"
            evaluation_dir.mkdir(parents=True, exist_ok=True)
            np.save(evaluation_dir / "metric_height_fused.npy", fused_metric_height)

        view_results = {
            "deg_0": (
                decoded_0.absolute.absolute_phase,
                decoded_0.height.height,
                decoded_0.height.mask,
                decoded_0.height.metric,
                phase_gt_0,
                height_gt_0,
                regions_0,
            ),
            "deg_180": (
                decoded_180.absolute.absolute_phase,
                decoded_180.height.height,
                decoded_180.height.mask,
                decoded_180.height.metric,
                phase_gt_180,
                height_gt_180,
                regions_180,
            ),
            "fused": (
                None,
                fused_metric_height if fused_metric_height is not None else fused.height.height,
                fused_metric_mask if fused_metric_mask is not None else fused.height.mask,
                fused_metric_height is not None,
                None,
                height_gt_0,
                regions_0,
            ),
        }
        summary_views: dict[str, Any] = {}
        for (
            view_name,
            (phase, height, valid, metric_height, view_phase_gt, view_height_gt, view_regions),
        ) in view_results.items():
            summary_views[view_name] = {
                "regions": evaluate_regions(
                    phase_prediction=phase,
                    phase_truth=view_phase_gt if phase is not None else None,
                    height_prediction=height if metric_height else None,
                    height_truth=view_height_gt if metric_height else None,
                    regions=view_regions,
                    valid=valid,
                )
            }
        cycle_detected = np.asarray(decoded_0.absolute.correction_mask, dtype=bool)
        cycle_expected = impairment_masks_0["cycle_slip"]
        summary_views["deg_0"]["cycle_slip_detection"] = detection_statistics(
            cycle_detected, cycle_expected, regions_0["pcb_all"]
        )
        fusion_rejected = ~np.asarray(fused.height.mask, dtype=bool)
        fusion_expected = impairment_masks_0["registration_error"]
        summary_views["fused"]["fusion_rejection"] = detection_statistics(
            fusion_rejected, fusion_expected, regions_0["pcb_all"]
        )

        summary = {
            "schema_version": 1,
            "validation_level": manifest.get("validation_level", "unknown"),
            "validation_kind": manifest.get("validation_kind", "unknown"),
            "real_world_accuracy_claim": False,
            "views": summary_views,
        }
        write_summary(output, summary)
        write_failures(output, failures)
        write_overview(
            output / "overview.png",
            prediction=fused_metric_height if fused_metric_height is not None else fused.height.height,
            truth=height_gt_0 if fused_metric_height is not None else None,
            valid=fused_metric_mask if fused_metric_mask is not None else fused.height.mask,
            title=(
                "synthetic metric-height validation overview (not hardware accuracy)"
                if fused_metric_height is not None
                else "synthetic phase-domain fusion overview; no metric calibration"
            ),
        )
        return summary
