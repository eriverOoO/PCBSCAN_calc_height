from __future__ import annotations

import argparse
from pathlib import Path

from .decoder import DecodeConfig, PcbFppDecoder


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
    parser.add_argument("--output", required=True, type=Path, help="Output processed folder")
    parser.add_argument("--projector-width", type=int, default=1280)
    parser.add_argument("--gray-bits", type=int, default=8)
    parser.add_argument("--min-signal", type=float, default=20.0)
    parser.add_argument("--saturation-threshold", type=float, default=250.0)
    parser.add_argument("--dark-threshold", type=float, default=5.0)
    parser.add_argument("--modulation-threshold", type=float, default=0.05)
    parser.add_argument(
        "--gray-threshold-mode",
        choices=("dynamic_raw", "normalized_0p5"),
        default="dynamic_raw",
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
    )
    parser.add_argument("--reference-scan", type=Path)
    parser.add_argument("--reference-phase", type=Path)
    parser.add_argument("--calibration-config", type=Path)
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
    parser.add_argument("--save-debug", action="store_true")
    parser.add_argument("--max-point-cloud-points", type=int, default=300_000)
    return parser


def config_from_args(args: argparse.Namespace) -> DecodeConfig:
    return DecodeConfig(
        projector_width=args.projector_width,
        gray_bits=args.gray_bits,
        min_signal=args.min_signal,
        saturation_threshold=args.saturation_threshold,
        dark_threshold=args.dark_threshold,
        modulation_threshold=args.modulation_threshold,
        gray_threshold_mode=args.gray_threshold_mode,
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
        save_debug=args.save_debug,
        max_point_cloud_points=args.max_point_cloud_points,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    decoder = PcbFppDecoder(config_from_args(args))
    if args.input_180:
        result = decoder.decode_fused(args.input, args.input_180, args.output)
        print(f"Decoded 0-degree scan: {args.input}")
        print(f"Decoded 180-degree scan: {args.input_180}")
        print(f"Output folder: {args.output}")
        print(
            "Fused valid ratio: "
            f"{result.report['fusion']['coverage']['fused_valid_ratio']:.3f}"
        )
        print(f"Height mode: {result.height.mode}; metric={result.height.metric}")
    else:
        result = decoder.decode(args.input, args.output)
        print(f"Decoded scan: {args.input}")
        print(f"Output folder: {args.output}")
        print(
            "Combined valid ratio: "
            f"{result.report['mask_coverage']['combined_mask_ratio']:.3f}"
        )
        print(f"Height mode: {result.height.mode}; metric={result.height.metric}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
