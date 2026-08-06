from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .aruco_alignment import (
    AlignmentResult,
    estimate_aruco_transform,
    estimate_stage_cross_transform_from_images,
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
    aruco_ids: Sequence[int] = (0, 1, 2, 3),
    aruco_image: str = "pattern_000.png",
    aruco_method: str = "homography",
    aruco_ransac_threshold_px: float = 3.0,
    phase_correlation_image: str = "pattern_000.png",
    phase_correlation_use_hann: bool = True,
    phase_correlation_min_response: float = 0.0,
) -> EstimatedFusionTransform | None:
    return estimate_and_save_view_transform(
        registration,
        input_dir,
        input_180_dir,
        output_dir,
        source_angle_deg=180,
        fusion_center=fusion_center,
        aruco_dictionary=aruco_dictionary,
        aruco_ids=aruco_ids,
        aruco_image=aruco_image,
        aruco_method=aruco_method,
        aruco_ransac_threshold_px=aruco_ransac_threshold_px,
        phase_correlation_image=phase_correlation_image,
        phase_correlation_use_hann=phase_correlation_use_hann,
        phase_correlation_min_response=phase_correlation_min_response,
    )


def estimate_and_save_view_transform(
    registration: str,
    target_dir: Path,
    source_dir: Path,
    output_dir: Path,
    *,
    source_angle_deg: int,
    fusion_center: tuple[float, float] | None = None,
    aruco_dictionary: str = "DICT_4X4_50",
    aruco_ids: Sequence[int] = (0, 1, 2, 3),
    aruco_image: str = "pattern_000.png",
    aruco_method: str = "stage-cross",
    aruco_marker_center_radius_mm: float = 25.0,
    aruco_marker_black_square_mm: float = 11.4,
    aruco_ransac_threshold_px: float = 3.0,
    phase_correlation_image: str = "pattern_000.png",
    phase_correlation_use_hann: bool = True,
    phase_correlation_min_response: float = 0.0,
) -> EstimatedFusionTransform | None:
    if registration == "rotation-180":
        if int(source_angle_deg) % 360 != 180:
            raise ValueError("rotation-180 registration only supports the 180-degree view")
        return None
    if registration not in FUSION_REGISTRATION_CHOICES:
        raise ValueError(
            "fusion registration must be one of "
            + ", ".join(FUSION_REGISTRATION_CHOICES)
        )

    fusion_dir = Path(output_dir) / "fusion"
    fusion_dir.mkdir(parents=True, exist_ok=True)

    if registration == "aruco":
        if aruco_method == "stage-cross":
            result = estimate_stage_cross_transform_from_images(
                Path(target_dir) / aruco_image,
                Path(source_dir) / aruco_image,
                dictionary_name=aruco_dictionary,
                marker_ids=list(aruco_ids),
                marker_center_radius_mm=aruco_marker_center_radius_mm,
                marker_black_square_mm=aruco_marker_black_square_mm,
                expected_rotation_deg=float(source_angle_deg),
                ransac_threshold_px=aruco_ransac_threshold_px,
            )
        else:
            result = estimate_aruco_transform(
                target_dir,
                source_dir,
                dictionary_name=aruco_dictionary,
                marker_ids=list(aruco_ids),
                image_name=aruco_image,
                method=aruco_method,
                ransac_threshold_px=aruco_ransac_threshold_px,
                expected_rotation_deg=float(source_angle_deg),
            )
        if int(source_angle_deg) % 360 == 180 and aruco_method != "stage-cross":
            output_path = fusion_dir / "aruco_fusion_transform.json"
        else:
            output_path = fusion_dir / f"aruco_transform_deg_{int(source_angle_deg) % 360}.json"
        save_aruco_alignment_json(
            output_path,
            result,
            input_dir=target_dir,
            input_180_dir=source_dir,
            dictionary_name=aruco_dictionary,
            image_name=aruco_image,
            method=aruco_method,
            ransac_threshold_px=aruco_ransac_threshold_px,
            target_angle_deg=0,
            source_angle_deg=source_angle_deg,
        )
        return _aruco_summary(output_path, result)

    if int(source_angle_deg) % 360 != 180:
        raise ValueError("phase-correlation registration currently supports only 180 degrees")

    result = estimate_phase_correlation_transform(
        target_dir,
        source_dir,
        image_name=phase_correlation_image,
        fusion_center=fusion_center,
        use_hann_window=phase_correlation_use_hann,
        min_response=phase_correlation_min_response,
    )
    output_path = fusion_dir / "phase_correlation_fusion_transform.json"
    save_phase_correlation_alignment_json(
        output_path,
        result,
        input_dir=target_dir,
        input_180_dir=source_dir,
        image_name=phase_correlation_image,
        use_hann_window=phase_correlation_use_hann,
    )
    return _phase_correlation_summary(output_path, result)


def _aruco_summary(
    output_path: Path,
    result: AlignmentResult,
) -> EstimatedFusionTransform:
    rotation = result.rotation_source_to_target_deg
    deviation = result.deviation_from_expected_deg
    details = (
        f"rmse={result.reprojection_rmse_px:.3f} px, "
        f"inlier_rmse={result.inlier_reprojection_rmse_px:.3f} px, "
        f"inliers={result.inlier_count}/{result.point_count}"
    )
    if rotation is not None and deviation is not None:
        details += (
            f", rotation={rotation:.4f} deg, "
            f"|deviation from {result.expected_rotation_deg:g}|={deviation:.4f} deg"
        )
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
