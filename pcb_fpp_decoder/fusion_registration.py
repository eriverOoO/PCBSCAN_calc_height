from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .aruco_alignment import (
    AlignmentResult,
    estimate_aruco_transform,
    save_alignment_json as save_aruco_alignment_json,
)
from .phase_correlation_alignment import (
    PhaseCorrelationAlignmentResult,
    estimate_phase_correlation_transform,
    save_alignment_json as save_phase_correlation_alignment_json,
)


FUSION_REGISTRATION_CHOICES = ("rotation-180", "aruco", "phase-correlation")


@dataclass(frozen=True)
class EstimatedFusionTransform:
    path: Path
    registration: str
    transform_kind: str
    summary: str


def estimate_and_save_fusion_transform(
    registration: str,
    input_dir: Path,
    input_180_dir: Path,
    output_dir: Path,
    *,
    fusion_center: tuple[float, float] | None = None,
    aruco_dictionary: str = "DICT_4X4_50",
    aruco_ids: Sequence[int] = (0, 1),
    aruco_image: str = "pattern_000.png",
    aruco_method: str = "homography",
    phase_correlation_image: str = "pattern_000.png",
    phase_correlation_use_hann: bool = True,
    phase_correlation_min_response: float = 0.0,
) -> EstimatedFusionTransform | None:
    if registration == "rotation-180":
        return None
    if registration not in FUSION_REGISTRATION_CHOICES:
        raise ValueError(
            "fusion registration must be one of "
            + ", ".join(FUSION_REGISTRATION_CHOICES)
        )

    fusion_dir = Path(output_dir) / "fusion"
    fusion_dir.mkdir(parents=True, exist_ok=True)

    if registration == "aruco":
        result = estimate_aruco_transform(
            input_dir,
            input_180_dir,
            dictionary_name=aruco_dictionary,
            marker_ids=list(aruco_ids),
            image_name=aruco_image,
            method=aruco_method,
        )
        output_path = fusion_dir / "aruco_fusion_transform.json"
        save_aruco_alignment_json(
            output_path,
            result,
            input_dir=input_dir,
            input_180_dir=input_180_dir,
            dictionary_name=aruco_dictionary,
            image_name=aruco_image,
            method=aruco_method,
        )
        return _aruco_summary(output_path, result)

    result = estimate_phase_correlation_transform(
        input_dir,
        input_180_dir,
        image_name=phase_correlation_image,
        fusion_center=fusion_center,
        use_hann_window=phase_correlation_use_hann,
        min_response=phase_correlation_min_response,
    )
    output_path = fusion_dir / "phase_correlation_fusion_transform.json"
    save_phase_correlation_alignment_json(
        output_path,
        result,
        input_dir=input_dir,
        input_180_dir=input_180_dir,
        image_name=phase_correlation_image,
        use_hann_window=phase_correlation_use_hann,
    )
    return _phase_correlation_summary(output_path, result)


def _aruco_summary(
    output_path: Path,
    result: AlignmentResult,
) -> EstimatedFusionTransform:
    rotation = result.rotation_source_to_target_deg
    deviation = result.deviation_from_180_deg
    details = f"rmse={result.reprojection_rmse_px:.3f} px"
    if rotation is not None and deviation is not None:
        details += f", rotation={rotation:.4f} deg, |deviation from 180|={deviation:.4f} deg"
    return EstimatedFusionTransform(
        path=output_path,
        registration="aruco",
        transform_kind=result.transform_kind,
        summary=f"ArUco {result.transform_kind} transform estimated ({details})",
    )


def _phase_correlation_summary(
    output_path: Path,
    result: PhaseCorrelationAlignmentResult,
) -> EstimatedFusionTransform:
    dx, dy = result.residual_shift_xy
    return EstimatedFusionTransform(
        path=output_path,
        registration="phase-correlation",
        transform_kind=result.transform_kind,
        summary=(
            "Phase-correlation affine transform estimated "
            f"(dx={dx:.3f} px, dy={dy:.3f} px, response={result.response:.3f})"
        ),
    )
