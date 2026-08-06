from __future__ import annotations

import argparse
from pathlib import Path

from .aruco_alignment import ARUCO_DICTIONARIES, parse_marker_ids
from .capture_contract import audit_capture_contract
from .decoder import DecodeConfig, OUTPUT_PROFILES, PcbFppDecoder
from .fusion_registration import (
    FUSION_REGISTRATION_CHOICES,
    estimate_and_save_fusion_transform,
    estimate_and_save_view_transform,
)
from .io import (
    COLOR_INPUT_MODES,
    FOUR_DIRECTION_ANGLES,
    has_decode_pattern_files,
    parse_crosstalk_matrix,
    resolve_decode_input_dir,
    resolve_multiview_scan_dirs,
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
    parser.add_argument("--input-90", type=Path, help="Optional 90-degree scan folder")
    parser.add_argument("--input-270", type=Path, help="Optional 270-degree scan folder")
    parser.add_argument(
        "--four-direction",
        action="store_true",
        help="Decode and fuse 0/90/180/270 folders from one scan root",
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
    parser.add_argument(
        "--require-hardware-capture",
        action="store_true",
        help=(
            "Reject input unless scan_log.json proves a locked hardware-triggered "
            "pattern/exposure sequence and fixed linear Mono camera settings."
        ),
    )
    parser.add_argument(
        "--stage-angle-tolerance-deg",
        type=float,
        default=0.5,
        help="Allowed commanded/measured stage angle error in strict four-view mode",
    )
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
        choices=("relative", "reference", "phase_linear", "triangulation", "inverse-linear"),
        default="relative",
        help=(
            "relative outputs phase units only; reference/phase_linear/triangulation/"
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
        "--reference-scan-0",
        type=Path,
        help="0-degree flat reference scan; overrides --reference-scan for the 0 view",
    )
    parser.add_argument("--reference-scan-90", type=Path, help="90-degree flat reference scan")
    parser.add_argument(
        "--reference-scan-180",
        type=Path,
        help="180-degree flat reference scan; overrides --reference-scan for the 180 view",
    )
    parser.add_argument("--reference-scan-270", type=Path, help="270-degree flat reference scan")
    parser.add_argument(
        "--reference-phase-0",
        type=Path,
        help="0-degree precomputed reference phase; overrides --reference-phase",
    )
    parser.add_argument("--reference-phase-90", type=Path, help="90-degree reference phase")
    parser.add_argument(
        "--reference-phase-180",
        type=Path,
        help="180-degree precomputed reference phase; overrides --reference-phase",
    )
    parser.add_argument("--reference-phase-270", type=Path, help="270-degree reference phase")
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
        "--fusion-max-height-difference-mm",
        type=float,
        default=0.25,
        help="Reject metric overlap blending above this absolute view difference",
    )
    parser.add_argument(
        "--fusion-inconsistent-policy",
        choices=("higher-confidence", "invalid"),
        default="higher-confidence",
        help="Resolve rejected overlap using the stronger view or mark it invalid",
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
        "--fusion-transform-90",
        type=Path,
        help="Transform mapping 90-degree pixels into the 0-degree frame",
    )
    parser.add_argument(
        "--fusion-transform-270",
        type=Path,
        help="Transform mapping 270-degree pixels into the 0-degree frame",
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
        choices=("stage-cross", "homography", "affine"),
        default="stage-cross",
        help="Transform model for ArUco marker registration",
    )
    parser.add_argument(
        "--aruco-marker-center-radius-mm",
        type=float,
        default=25.0,
        help="Stage-cross marker center radius; r25 PDF uses 25 mm",
    )
    parser.add_argument(
        "--aruco-marker-black-square-mm",
        type=float,
        default=11.4,
        help="Printed black ArUco square size; total15/quiet1.8 layout uses 11.4 mm",
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
        default=25.0,
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
        "--pcb-inset-mm",
        type=float,
        default=0.5,
        help=(
            "Safety band excluded inside the PCB outline to prevent exposed stage paper "
            "from entering height analysis. Default: 0.5."
        ),
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
    parser.add_argument(
        "--output-profile",
        choices=OUTPUT_PROFILES,
        default="compact",
        help=(
            "compact saves reports, previews, and essential phase/height arrays; "
            "full also saves corrected frames, raw intermediate arrays, and PLY point clouds."
        ),
    )
    parser.add_argument("--max-point-cloud-points", type=int, default=300_000)
    return parser


def config_from_args(args: argparse.Namespace) -> DecodeConfig:
    analysis_roi_mode = args.analysis_roi

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
        reference_scan_0=args.reference_scan_0,
        reference_scan_90=args.reference_scan_90,
        reference_scan_180=args.reference_scan_180,
        reference_scan_270=args.reference_scan_270,
        reference_phase_0=args.reference_phase_0,
        reference_phase_90=args.reference_phase_90,
        reference_phase_180=args.reference_phase_180,
        reference_phase_270=args.reference_phase_270,
        calibration_config=args.calibration_config,
        height_sign=args.height_sign,
        fusion_mode=args.fusion_mode,
        fusion_max_height_difference_mm=args.fusion_max_height_difference_mm,
        fusion_inconsistent_policy=args.fusion_inconsistent_policy,
        fusion_center=tuple(args.fusion_center) if args.fusion_center else None,
        fusion_transform=args.fusion_transform,
        fusion_transform_90=args.fusion_transform_90,
        fusion_transform_270=args.fusion_transform_270,
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
        pcb_inset_mm=args.pcb_inset_mm,
        output_profile=args.output_profile,
        save_debug=args.save_debug,
        max_point_cloud_points=args.max_point_cloud_points,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    selected_input = args.input
    four_direction = bool(args.four_direction or args.input_90 or args.input_270)
    multiview_inputs: dict[int, Path] | None = None
    if four_direction:
        multiview_inputs = resolve_multiview_scan_dirs(selected_input)
        explicit = {90: args.input_90, 180: args.input_180, 270: args.input_270}
        for angle, path in explicit.items():
            if path is not None:
                multiview_inputs[angle] = resolve_decode_input_dir(path, preferred_angle=angle)
        if 0 not in multiview_inputs:
            candidate_0 = resolve_decode_input_dir(selected_input, preferred_angle=0)
            if has_decode_pattern_files(candidate_0):
                multiview_inputs[0] = candidate_0
        missing = [angle for angle in FOUR_DIRECTION_ANGLES if angle not in multiview_inputs]
        if missing:
            parser.error(f"four-direction scan is missing decoder-ready angles: {missing}")
        args.input = multiview_inputs[0]
        args.input_90 = multiview_inputs[90]
        args.input_180 = multiview_inputs[180]
        args.input_270 = multiview_inputs[270]
    else:
        args.input = resolve_decode_input_dir(selected_input, preferred_angle=args.input_angle)
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

    if args.require_hardware_capture:
        try:
            if multiview_inputs is not None:
                for angle, path in multiview_inputs.items():
                    _require_hardware_capture(
                        path,
                        expected_angle=angle,
                        stage_angle_tolerance_deg=args.stage_angle_tolerance_deg,
                    )
            else:
                _require_hardware_capture(args.input)
                if args.input_180:
                    _require_hardware_capture(args.input_180)
        except ValueError as exc:
            parser.error(str(exc))

    config = config_from_args(args)
    try:
        estimated_transforms = []
        if multiview_inputs is not None:
            estimated_transforms = _prepare_multiview_registration(args, config, multiview_inputs)
        elif args.input_180:
            estimated = _prepare_fusion_registration(args, config)
            estimated_transforms = [estimated] if estimated is not None else []
        decoder = PcbFppDecoder(config)
        if multiview_inputs is not None:
            result = decoder.decode_multiview(multiview_inputs, args.output)
        elif args.input_180:
            result = decoder.decode_fused(args.input, args.input_180, args.output)
        else:
            result = decoder.decode(args.input, args.output)
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        parser.error(str(exc))

    if multiview_inputs is not None:
        for angle, path in multiview_inputs.items():
            print(f"Decoded {angle}-degree scan: {path}")
        print(f"Output folder: {args.output}")
        for estimated in estimated_transforms:
            print(estimated.summary)
            print(f"Fusion transform: {estimated.path}")
        print(
            "Four-view fused valid ratio: "
            f"{result.report['fusion']['coverage']['fused_valid_ratio']:.3f}"
        )
        print(f"Height mode: {result.height.mode}; metric={result.height.metric}")
    elif args.input_180:
        print(f"Decoded 0-degree scan: {args.input}")
        print(f"Decoded 180-degree scan: {args.input_180}")
        print(f"Output folder: {args.output}")
        for estimated in estimated_transforms:
            print(estimated.summary)
            print(f"Fusion transform: {estimated.path}")
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
    print(f"Capture diagnosis: {args.output / 'capture_diagnosis.txt'}")
    return 0


def _require_hardware_capture(
    input_dir: Path,
    *,
    expected_angle: float | None = None,
    stage_angle_tolerance_deg: float = 0.5,
) -> None:
    audit = audit_capture_contract(
        input_dir,
        expected_view_angle_deg=expected_angle,
        stage_angle_tolerance_deg=stage_angle_tolerance_deg,
    )
    if audit["status"] == "passed":
        return
    details = "\n- ".join(str(error) for error in audit["errors"])
    raise ValueError(
        "--require-hardware-capture rejected the scan. "
        "Run scripts/verify_hardware_capture.py for the JSON audit.\n- " + details
    )


def _prepare_fusion_registration(
    args: argparse.Namespace,
    config: DecodeConfig,
):
    if args.fusion_registration == "precomputed":
        if config.fusion_transform is None:
            raise ValueError("precomputed registration requires --fusion-transform")
        return None
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
        aruco_marker_center_radius_mm=args.aruco_marker_center_radius_mm,
        aruco_marker_black_square_mm=args.aruco_marker_black_square_mm,
        aruco_ransac_threshold_px=args.aruco_ransac_threshold_px,
        phase_correlation_image=args.phase_correlation_image,
        phase_correlation_min_response=args.phase_correlation_min_response,
    )
    if estimated_transform is not None:
        config.fusion_transform = estimated_transform.path
    return estimated_transform


def _prepare_multiview_registration(
    args: argparse.Namespace,
    config: DecodeConfig,
    input_dirs: dict[int, Path],
):
    if args.fusion_registration == "precomputed":
        missing = []
        if config.fusion_transform_90 is None:
            missing.append("--fusion-transform-90")
        if config.fusion_transform is None:
            missing.append("--fusion-transform")
        if config.fusion_transform_270 is None:
            missing.append("--fusion-transform-270")
        if missing:
            raise ValueError("precomputed four-direction registration requires " + ", ".join(missing))
        return []
    if args.fusion_registration != "aruco":
        raise ValueError(
            "four-direction automatic registration requires --fusion-registration aruco; "
            "use precomputed with three angle-specific transforms otherwise"
        )
    if any(
        path is not None
        for path in (config.fusion_transform_90, config.fusion_transform, config.fusion_transform_270)
    ):
        raise ValueError(
            "angle-specific fusion transforms cannot be combined with automatic ArUco registration"
        )

    marker_ids = parse_marker_ids(args.aruco_ids)
    estimated = []
    for angle in (90, 180, 270):
        transform = estimate_and_save_view_transform(
            "aruco",
            input_dirs[0],
            input_dirs[angle],
            args.output,
            source_angle_deg=angle,
            fusion_center=config.fusion_center,
            aruco_dictionary=args.aruco_dictionary,
            aruco_ids=marker_ids,
            aruco_image=args.aruco_image,
            aruco_method=args.aruco_method,
            aruco_marker_center_radius_mm=args.aruco_marker_center_radius_mm,
            aruco_marker_black_square_mm=args.aruco_marker_black_square_mm,
            aruco_ransac_threshold_px=args.aruco_ransac_threshold_px,
        )
        if transform is None:
            raise ValueError(f"failed to estimate the {angle}-degree ArUco transform")
        estimated.append(transform)
        if angle == 90:
            config.fusion_transform_90 = transform.path
        elif angle == 180:
            config.fusion_transform = transform.path
        else:
            config.fusion_transform_270 = transform.path
    return estimated


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
