from __future__ import annotations

import argparse
from pathlib import Path

from .aruco_alignment import ARUCO_DICTIONARIES, parse_marker_ids
from .decoder import DecodeConfig, PcbFppDecoder
from .fusion_registration import (
    FUSION_REGISTRATION_CHOICES,
    estimate_and_save_fusion_transform,
)
from .io import (
    COLOR_INPUT_MODES,
    has_decode_pattern_files,
    parse_crosstalk_matrix,
    resolve_decode_input_dir,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Decode a 14-pattern PCB structured-light/FPP scan."
    )
    parser.add_argument("--input", required=True, type=Path, help="Input scan folder")
    parser.add_argument(
        "--input-180",
        type=Path,
        help="Optional 180-degree scan folder to fuse with --input",
    )
    parser.add_argument(
        "--input-angle",
        type=int,
        help=(
            "When --input is a PRO4500 phone scan root, decode this angle_NNN folder. "
            "If omitted, decoder-ready input is used directly or angle_000 is preferred."
        ),
    )
    parser.add_argument(
        "--input-180-angle",
        type=int,
        default=180,
        help="When --input-180 or --input is a PRO4500 scan root, use this 180-view angle.",
    )
    parser.add_argument(
        "--auto-phone-fusion",
        action="store_true",
        help=(
            "If --input is a PRO4500 phone scan root containing angle_000 and "
            "angle_180 decode folders, fuse them without passing --input-180."
        ),
    )
    parser.add_argument("--output", required=True, type=Path, help="Output processed folder")
    parser.add_argument("--projector-width", type=int, default=1280)
    parser.add_argument("--gray-bits", type=int, default=8)
    parser.add_argument(
        "--input-color-mode",
        choices=COLOR_INPUT_MODES,
        default="smartphone_uv_blue",
        help=(
            "How RGB camera frames are converted to one FPP intensity image. "
            "Use smartphone_uv_blue/blue for Galaxy UV pattern captures to isolate "
            "red-channel UV leakage and magenta cast."
        ),
    )
    parser.add_argument(
        "--color-crosstalk-matrix",
        type=_parse_crosstalk_matrix_arg,
        help=(
            "Optional 3x3 kappa matrix for RGB crosstalk decoupling before channel "
            "extraction. Format: 'r1c1,r1c2,r1c3;r2c1,...;r3c1,...'."
        ),
    )
    parser.add_argument("--min-signal", type=float, default=20.0)
    parser.add_argument("--saturation-threshold", type=float, default=250.0)
    parser.add_argument("--dark-threshold", type=float, default=5.0)
    parser.add_argument("--modulation-threshold", type=float, default=0.05)
    parser.add_argument(
        "--gray-threshold-mode",
        choices=("dynamic_raw", "normalized_0p5"),
        default="dynamic_raw",
    )
    parser.add_argument(
        "--gray-decode-mode",
        choices=("auto", "normal", "inverted_pair"),
        default="auto",
        help="Use inverted Gray pairs when ids 14..21 are present, or force a mode",
    )
    parser.add_argument(
        "--gray-pair-min-contrast",
        type=float,
        default=0.05,
        help="Minimum normalized normal/inverted Gray difference for valid pair bits",
    )
    parser.add_argument("--sine-source", choices=("corrected", "raw"), default="corrected")
    parser.add_argument(
        "--phase-convention",
        choices=("default", "negated", "swapped"),
        default="default",
    )
    parser.add_argument(
        "--phase-direction", choices=("normal", "reverse"), default="normal"
    )
    parser.add_argument("--apply-half-period-correction", action="store_true")
    parser.add_argument("--boundary-margin", type=float, default=0.35)
    parser.add_argument("--detrend", action="store_true")
    parser.add_argument("--median-filter", type=int, default=0)
    parser.add_argument(
        "--height-mode",
        choices=("relative", "reference", "triangulation", "inverse-linear"),
        default="relative",
        help=(
            "relative uses absolute phase preview only; reference/triangulation/"
            "inverse-linear require a flat reference phase to cancel projector keystone"
        ),
    )
    parser.add_argument(
        "--reference-scan",
        type=Path,
        help="Flat PCB/reference-plane scan folder used for phi_object - phi_reference",
    )
    parser.add_argument(
        "--reference-phase",
        type=Path,
        help="Precomputed flat reference absolute_phase.npy used for keystone cancellation",
    )
    parser.add_argument(
        "--calibration-config",
        type=Path,
        help="JSON/NPZ calibration. Triangulation accepts scalar or map d/l/p parameters.",
    )
    parser.add_argument("--height-sign", type=float, default=1.0, choices=(-1.0, 1.0))
    parser.add_argument(
        "--fusion-mode",
        choices=("average", "modulation-weighted"),
        default="modulation-weighted",
        help="How to combine pixels valid in both 0 and 180 degree scans",
    )
    parser.add_argument(
        "--fusion-center",
        nargs=2,
        type=float,
        metavar=("X", "Y"),
        help="Rotation center in output pixels for default 180-degree alignment",
    )
    parser.add_argument(
        "--fusion-transform",
        type=Path,
        help="JSON/NPY/NPZ 2x3 affine or 3x3 homography mapping 180-degree pixels to 0-degree pixels",
    )
    parser.add_argument(
        "--fusion-registration",
        choices=FUSION_REGISTRATION_CHOICES,
        default="aruco",
        help=(
            "Estimate a fusion transform automatically before decoding. "
            "rotation-180 uses the nominal center rotation; aruco detects markers; "
            "phase-correlation refines residual x/y translation. Default: aruco."
        ),
    )
    parser.add_argument(
        "--aruco-dictionary",
        default="DICT_4X4_50",
        choices=sorted(ARUCO_DICTIONARIES),
        help="ArUco dictionary for --fusion-registration aruco",
    )
    parser.add_argument(
        "--aruco-ids",
        default="0,1,2,3",
        help="Comma-separated ArUco marker IDs for --fusion-registration aruco",
    )
    parser.add_argument(
        "--aruco-image",
        default="pattern_000.png",
        help="Image file used for ArUco marker detection",
    )
    parser.add_argument(
        "--aruco-method",
        choices=("homography", "affine"),
        default="homography",
        help="Transform model for ArUco marker registration",
    )
    parser.add_argument(
        "--aruco-ransac-threshold-px",
        type=float,
        default=3.0,
        help="RANSAC reprojection threshold in pixels for ArUco registration",
    )
    parser.add_argument(
        "--analysis-roi",
        choices=("none", "aruco"),
        default="aruco",
        help=(
            "Limit decoding to an analysis ROI. Default: aruco. Use none for scans "
            "without stage markers."
        ),
    )
    parser.add_argument(
        "--analysis-aruco-dictionary",
        default="DICT_4X4_50",
        choices=sorted(ARUCO_DICTIONARIES),
        help="ArUco dictionary for --analysis-roi aruco",
    )
    parser.add_argument(
        "--analysis-aruco-ids",
        type=_parse_marker_id_tuple_arg,
        default=(0, 1, 2, 3),
        help="Exactly four comma-separated ArUco marker IDs for analysis ROI",
    )
    parser.add_argument(
        "--analysis-aruco-image",
        default="pattern_000.png",
        help="Image file used for analysis ROI marker detection",
    )
    parser.add_argument(
        "--analysis-aruco-layout",
        choices=("corners", "stage-cross"),
        default="stage-cross",
        help=(
            "corners treats four markers as workspace corners; stage-cross treats "
            "IDs as top,right,bottom,left around the rotation stage center. "
            "Default: stage-cross."
        ),
    )
    parser.add_argument(
        "--analysis-workspace-width-mm",
        type=float,
        help="Physical width between the four marker-space corners, in millimeters",
    )
    parser.add_argument(
        "--analysis-workspace-height-mm",
        type=float,
        help="Physical height between the four marker-space corners, in millimeters",
    )
    parser.add_argument(
        "--analysis-marker-center-radius-mm",
        type=float,
        default=30.0,
        help="For --analysis-aruco-layout stage-cross, marker center radius from stage center",
    )
    parser.add_argument(
        "--analysis-stage-diameter-mm",
        type=float,
        default=105.0,
        help="For --analysis-aruco-layout stage-cross, optional stage diameter in millimeters",
    )
    parser.add_argument(
        "--pcb-width-mm",
        type=float,
        default=30.0,
        help="PCB width in millimeters. Default: 30.",
    )
    parser.add_argument(
        "--pcb-height-mm",
        type=float,
        default=30.0,
        help="PCB height in millimeters. Default: 30.",
    )
    parser.add_argument(
        "--pcb-margin-mm",
        type=float,
        default=0.0,
        help="Extra margin added around the centered PCB analysis area, in millimeters.",
    )
    parser.add_argument(
        "--phase-correlation-image",
        default="pattern_000.png",
        help="Image file used for phase-correlation registration",
    )
    parser.add_argument(
        "--phase-correlation-min-response",
        type=float,
        default=0.0,
        help="Fail phase-correlation registration below this response",
    )
    parser.add_argument("--save-debug", action="store_true")
    parser.add_argument("--max-point-cloud-points", type=int, default=300_000)
    return parser


def config_from_args(args: argparse.Namespace) -> DecodeConfig:
    analysis_roi_mode = args.analysis_roi
    analysis_options_given = any(
        value is not None
        for value in (
            args.analysis_workspace_width_mm,
            args.analysis_workspace_height_mm,
            args.analysis_marker_center_radius_mm,
            args.analysis_stage_diameter_mm,
            args.pcb_width_mm,
            args.pcb_height_mm,
            args.pcb_margin_mm if args.pcb_margin_mm else None,
        )
    )
    if analysis_roi_mode == "none" and analysis_options_given:
        analysis_roi_mode = "aruco"

    return DecodeConfig(
        projector_width=args.projector_width,
        gray_bits=args.gray_bits,
        input_color_mode=args.input_color_mode,
        color_crosstalk_matrix=args.color_crosstalk_matrix,
        min_signal=args.min_signal,
        saturation_threshold=args.saturation_threshold,
        dark_threshold=args.dark_threshold,
        modulation_threshold=args.modulation_threshold,
        gray_decode_mode=args.gray_decode_mode,
        gray_threshold_mode=args.gray_threshold_mode,
        gray_pair_min_contrast=args.gray_pair_min_contrast,
        sine_source=args.sine_source,
        phase_convention=args.phase_convention,
        phase_direction=args.phase_direction,
        apply_half_period_correction=args.apply_half_period_correction,
        boundary_margin=args.boundary_margin,
        detrend=args.detrend,
        median_filter=args.median_filter,
        height_mode=args.height_mode,
        reference_scan=args.reference_scan,
        reference_phase=args.reference_phase,
        calibration_config=args.calibration_config,
        height_sign=args.height_sign,
        fusion_mode=args.fusion_mode,
        fusion_center=tuple(args.fusion_center) if args.fusion_center else None,
        fusion_transform=args.fusion_transform,
        analysis_roi_mode=analysis_roi_mode,
        analysis_aruco_dictionary=args.analysis_aruco_dictionary,
        analysis_aruco_ids=tuple(args.analysis_aruco_ids),
        analysis_aruco_image=args.analysis_aruco_image,
        analysis_aruco_layout=args.analysis_aruco_layout,
        analysis_workspace_width_mm=args.analysis_workspace_width_mm,
        analysis_workspace_height_mm=args.analysis_workspace_height_mm,
        analysis_marker_center_radius_mm=args.analysis_marker_center_radius_mm,
        analysis_stage_diameter_mm=args.analysis_stage_diameter_mm,
        pcb_width_mm=args.pcb_width_mm,
        pcb_height_mm=args.pcb_height_mm,
        pcb_margin_mm=args.pcb_margin_mm,
        save_debug=args.save_debug,
        max_point_cloud_points=args.max_point_cloud_points,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.input = resolve_decode_input_dir(args.input, preferred_angle=args.input_angle)
    if args.input_180 is not None:
        args.input_180 = resolve_decode_input_dir(
            args.input_180,
            preferred_angle=args.input_180_angle,
        )
    elif args.auto_phone_fusion:
        candidate = resolve_decode_input_dir(args.input.parent, preferred_angle=args.input_180_angle)
        if candidate == args.input or not has_decode_pattern_files(candidate):
            candidate = resolve_decode_input_dir(args.input, preferred_angle=args.input_180_angle)
        if candidate == args.input or not has_decode_pattern_files(candidate):
            raise SystemExit(
                "--auto-phone-fusion could not find a decoder-ready "
                f"angle_{args.input_180_angle:03d} folder"
            )
        args.input_180 = candidate

    config = config_from_args(args)
    try:
        estimated_transform = _prepare_fusion_registration(args, config) if args.input_180 else None
        decoder = PcbFppDecoder(config)
        if args.input_180:
            result = decoder.decode_fused(args.input, args.input_180, args.output)
        else:
            result = decoder.decode(args.input, args.output)
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        parser.error(str(exc))

    if args.input_180:
        print(f"Decoded 0-degree scan: {args.input}")
        print(f"Decoded 180-degree scan: {args.input_180}")
        print(f"Output folder: {args.output}")
        if estimated_transform is not None:
            print(estimated_transform.summary)
            print(f"Fusion transform: {estimated_transform.path}")
        print(
            "Fused valid ratio: "
            f"{result.report['fusion']['coverage']['fused_valid_ratio']:.3f}"
        )
        print(f"Height mode: {result.height.mode}; metric={result.height.metric}")
    else:
        print(f"Decoded scan: {args.input}")
        print(f"Output folder: {args.output}")
        print(
            "Combined valid ratio: "
            f"{result.report['mask_coverage']['combined_mask_ratio']:.3f}"
        )
        print(f"Height mode: {result.height.mode}; metric={result.height.metric}")
    return 0


def _prepare_fusion_registration(
    args: argparse.Namespace,
    config: DecodeConfig,
):
    if args.fusion_registration == "rotation-180":
        return None
    if not args.input_180:
        raise ValueError("--fusion-registration requires --input-180")
    if args.fusion_transform is not None:
        raise ValueError(
            "--fusion-transform cannot be combined with --fusion-registration; "
            "choose either a precomputed transform or automatic registration"
        )

    marker_ids = parse_marker_ids(args.aruco_ids) if args.fusion_registration == "aruco" else ()
    estimated_transform = estimate_and_save_fusion_transform(
        args.fusion_registration,
        args.input,
        args.input_180,
        args.output,
        fusion_center=config.fusion_center,
        aruco_dictionary=args.aruco_dictionary,
        aruco_ids=marker_ids,
        aruco_image=args.aruco_image,
        aruco_method=args.aruco_method,
        aruco_ransac_threshold_px=args.aruco_ransac_threshold_px,
        phase_correlation_image=args.phase_correlation_image,
        phase_correlation_min_response=args.phase_correlation_min_response,
    )
    if estimated_transform is not None:
        config.fusion_transform = estimated_transform.path
    return estimated_transform


def _parse_crosstalk_matrix_arg(text: str):
    try:
        return parse_crosstalk_matrix(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _parse_marker_id_tuple_arg(text: str) -> tuple[int, ...]:
    try:
        return tuple(parse_marker_ids(text))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


if __name__ == "__main__":
    raise SystemExit(main())
