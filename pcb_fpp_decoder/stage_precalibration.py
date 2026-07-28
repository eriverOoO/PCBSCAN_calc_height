from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .aruco_alignment import (
    ARUCO_DICTIONARIES,
    AlignmentResult,
    estimate_aruco_transform_from_images,
    parse_marker_ids,
    save_alignment_json,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create a reusable nominal-180-degree fusion transform from two "
            "no-pattern ArUco images. The rotated image is captured after a "
            "stage command value such as 250; that value is not an angle."
        )
    )
    parser.add_argument("--image-0", required=True, type=Path, help="No-pattern image at stage value 0")
    parser.add_argument(
        "--image-rotated",
        required=True,
        type=Path,
        help="No-pattern image after the nominal-180-degree stage command",
    )
    parser.add_argument("--output", required=True, type=Path, help="Output reusable fusion-transform JSON")
    parser.add_argument(
        "--stage-command-value",
        type=float,
        default=250.0,
        help="Program value sent to the stage; it is not degrees (default: 250)",
    )
    parser.add_argument(
        "--intended-rotation-deg",
        type=float,
        default=180.0,
        help="Physical rotation intended by the stage command (default: 180)",
    )
    parser.add_argument(
        "--dictionary", default="DICT_4X4_50", choices=sorted(ARUCO_DICTIONARIES), help="OpenCV ArUco dictionary"
    )
    parser.add_argument("--ids", default="0,1,2,3", help="Comma-separated marker IDs")
    parser.add_argument(
        "--method", choices=("homography", "affine"), default="homography", help="Fusion warp model"
    )
    parser.add_argument("--ransac-threshold-px", type=float, default=3.0)
    return parser


def save_stage_precalibration_json(
    output_path: Path,
    result: AlignmentResult,
    *,
    image_0: Path,
    image_rotated: Path,
    stage_command_value: float,
    intended_rotation_deg: float,
    dictionary_name: str,
    method: str,
    ransac_threshold_px: float,
) -> None:
    """Save a decoder-compatible fusion transform plus auditable prescan data."""
    save_alignment_json(
        output_path,
        result,
        input_dir=image_0.parent,
        input_180_dir=image_rotated.parent,
        dictionary_name=dictionary_name,
        image_name=image_0.name,
        method=method,
        ransac_threshold_px=ransac_threshold_px,
    )
    payload: dict[str, Any] = json.loads(output_path.read_text(encoding="utf-8"))
    payload["source"] = {"role": "stage-rotated", "image": str(image_rotated)}
    payload["target"] = {"role": "stage-0", "image": str(image_0)}
    payload["stage_precalibration"] = {
        "commanded_stage_value": float(stage_command_value),
        "intended_rotation_deg": float(intended_rotation_deg),
        "actual_rotation_magnitude_deg": (
            abs(float(result.rotation_source_to_target_deg))
            if result.rotation_source_to_target_deg is not None
            else None
        ),
        "source_to_target_rotation_deg": result.rotation_source_to_target_deg,
        "rotation_center_target_xy": result.rotation_center_target_xy,
        "similarity_scale": result.similarity_scale,
        "usage": (
            "Maps pixels from the stage-rotated structured-light scan into the "
            "stage-0 scan. Keep the PCB fixed after these two prescan images."
        ),
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        marker_ids = parse_marker_ids(args.ids)
        result = estimate_aruco_transform_from_images(
            args.image_0,
            args.image_rotated,
            dictionary_name=args.dictionary,
            marker_ids=marker_ids,
            method=args.method,
            ransac_threshold_px=args.ransac_threshold_px,
        )
        save_stage_precalibration_json(
            args.output,
            result,
            image_0=args.image_0,
            image_rotated=args.image_rotated,
            stage_command_value=args.stage_command_value,
            intended_rotation_deg=args.intended_rotation_deg,
            dictionary_name=args.dictionary,
            method=args.method,
            ransac_threshold_px=args.ransac_threshold_px,
        )
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        raise SystemExit(f"error: {exc}") from exc

    print(f"Saved stage precalibration: {args.output}")
    print(f"Commanded stage value: {args.stage_command_value:g} (not degrees)")
    print(f"Intended physical rotation: {args.intended_rotation_deg:g} deg")
    if result.rotation_source_to_target_deg is not None:
        print(
            "Actual rotation magnitude: "
            f"{abs(result.rotation_source_to_target_deg):.4f} deg "
            f"(source->0 mapping {result.rotation_source_to_target_deg:.4f} deg)"
        )
    if result.rotation_center_target_xy is not None:
        x, y = result.rotation_center_target_xy
        print(f"Rotation center in 0-degree image: x={x:.3f}, y={y:.3f} px")
    print(f"Reprojection RMSE: {result.reprojection_rmse_px:.3f} px")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
