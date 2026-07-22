from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pcb_fpp_decoder.decoder import DecodeConfig, PcbFppDecoder
from pcb_fpp_decoder.validation import manifest_summary, write_synthetic_validation_outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Decode and validate synthetic 0/180 scans")
    parser.add_argument("--object-0", required=True, type=Path)
    parser.add_argument("--object-180", required=True, type=Path)
    parser.add_argument("--reference-0", required=True, type=Path)
    parser.add_argument("--reference-180", required=True, type=Path)
    parser.add_argument("--ground-truth-0", required=True, type=Path)
    parser.add_argument("--ground-truth-180", required=True, type=Path)
    parser.add_argument("--pcb-mask", required=True, type=Path)
    parser.add_argument("--calibration", required=True, type=Path)
    parser.add_argument("--object-manifest", required=True, type=Path)
    parser.add_argument("--reference-manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = DecodeConfig(
        height_mode="phase_linear",
        reference_scan_0=args.reference_0,
        reference_scan_180=args.reference_180,
        calibration_config=args.calibration,
        phase_convention="swapped",
        min_signal=5.0,
        median_filter=3,
        detrend=False,
        analysis_roi_mode="none",
        fusion_max_height_difference_mm=0.25,
        fusion_inconsistent_policy="higher-confidence",
        output_profile="compact",
    )
    fusion = PcbFppDecoder(config).decode_fused(
        args.object_0, args.object_180, args.output
    )

    # Ground truth enters only after decode_fused has completed.
    ground_truth = np.load(args.ground_truth_0).astype(np.float32)
    ground_truth_180_aligned = np.rot90(
        np.load(args.ground_truth_180).astype(np.float32), 2
    )
    pcb_mask = np.asarray(Image.open(args.pcb_mask)) > 0
    report = write_synthetic_validation_outputs(
        fusion,
        args.output,
        ground_truth,
        pcb_mask,
        manifests={
            "object": manifest_summary(args.object_manifest),
            "reference": manifest_summary(args.reference_manifest),
        },
        ground_truth_180_aligned=ground_truth_180_aligned,
    )
    overall = report["regions"]["overall_pcb"]
    tall = report["regions"]["components_ge_1mm"]
    print(f"PCB valid ratio: {overall['valid_ratio']:.6f}")
    print(f">=1 mm component valid ratio: {tall['valid_ratio']:.6f}")
    print(f"MAE: {overall['mae_mm']:.6f} mm")
    print(f"RMSE: {overall['rmse_mm']:.6f} mm")
    print(f"P95 absolute error: {overall['p95_absolute_error_mm']:.6f} mm")
    print(f"Accuracy report: {args.output / 'accuracy_report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
