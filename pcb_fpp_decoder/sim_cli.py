from __future__ import annotations

import argparse
from pathlib import Path

from .simulator import PcbFppSimulator, SyntheticPcbConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a synthetic PCB FPP scan, decode it with the existing decoder, "
            "and compare decoded results against ground truth."
        )
    )
    parser.add_argument("--output", required=True, type=Path, help="Simulation output root")
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=200)
    parser.add_argument("--stripe-width-px", type=float, default=5.0)
    parser.add_argument("--gray-bits", type=int, default=8)
    parser.add_argument("--height-scale", type=float, default=1.0)
    parser.add_argument("--trace-height", type=float, default=0.20)
    parser.add_argument("--pad-height", type=float, default=0.45)
    parser.add_argument("--component-height", type=float, default=0.90)
    parser.add_argument("--plane-tilt-x", type=float, default=0.0)
    parser.add_argument("--plane-tilt-y", type=float, default=0.0)
    parser.add_argument("--calibration-d", type=float, default=300.0)
    parser.add_argument("--calibration-l", type=float, default=120.0)
    parser.add_argument("--calibration-p", type=float, default=5.0)
    parser.add_argument("--height-sign", type=float, default=1.0, choices=(-1.0, 1.0))
    parser.add_argument("--noise-sigma", type=float, default=0.0)
    parser.add_argument("--blur-sigma", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--median-filter", type=int, default=0)
    parser.add_argument("--max-point-cloud-points", type=int, default=300_000)
    parser.add_argument(
        "--no-inverted-gray",
        action="store_true",
        help="Generate only the required 14 patterns instead of 22 patterns.",
    )
    parser.add_argument(
        "--add-defects",
        action="store_true",
        help="Add synthetic shadow and saturation areas that should be masked out.",
    )
    parser.add_argument(
        "--boundary-correction",
        action="store_true",
        help="Enable the decoder half-period boundary correction.",
    )
    parser.add_argument(
        "--detrend",
        action="store_true",
        help="Enable decoder plane detrending before accuracy comparison.",
    )
    return parser


def config_from_args(args: argparse.Namespace) -> SyntheticPcbConfig:
    return SyntheticPcbConfig(
        width=args.width,
        height=args.height,
        gray_bits=args.gray_bits,
        stripe_width_px=args.stripe_width_px,
        height_scale=args.height_scale,
        trace_height=args.trace_height,
        pad_height=args.pad_height,
        component_height=args.component_height,
        plane_tilt_x=args.plane_tilt_x,
        plane_tilt_y=args.plane_tilt_y,
        calibration_d=args.calibration_d,
        calibration_l=args.calibration_l,
        calibration_p=args.calibration_p,
        height_sign=args.height_sign,
        include_inverted_gray=not args.no_inverted_gray,
        add_defects=args.add_defects,
        noise_sigma=args.noise_sigma,
        blur_sigma=args.blur_sigma,
        random_seed=args.seed,
        apply_half_period_correction=args.boundary_correction,
        median_filter=args.median_filter,
        detrend=args.detrend,
        max_point_cloud_points=args.max_point_cloud_points,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = PcbFppSimulator(config_from_args(args)).run(args.output)
    height = result.report["metrics"]["height"]
    phase = result.report["metrics"]["absolute_phase"]
    stripe = result.report["metrics"]["stripe_order"]

    print(f"Simulation output: {result.output_root}")
    print(f"Synthetic object scan: {result.object_scan_dir}")
    print(f"Decoded output: {result.processed_object_dir}")
    print(f"Truth maps: {result.truth_dir}")
    print(f"Accuracy report: {result.output_root / 'simulation_report.json'}")
    print(
        "Height RMSE: "
        f"{height['rmse'] if height['rmse'] is not None else 'n/a'}; "
        f"MAE: {height['mae'] if height['mae'] is not None else 'n/a'}"
    )
    print(
        "Absolute phase RMSE: "
        f"{phase['rmse'] if phase['rmse'] is not None else 'n/a'}"
    )
    print(
        "Stripe exact ratio: "
        f"{stripe['exact_ratio'] if stripe['exact_ratio'] is not None else 'n/a'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
