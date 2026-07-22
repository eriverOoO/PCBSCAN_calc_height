from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validation_harness.ideal import BOARD_PROFILES, IdealDatasetConfig, generate_ideal_dataset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a deterministic ideal 4-view, exact 22-pattern PCB dataset"
    )
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=320)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--projector-period-px", type=float, default=24.0)
    parser.add_argument("--height-shift-px-per-mm", type=float, default=1.8)
    parser.add_argument("--board-profile", choices=BOARD_PROFILES, default="procedural_generic")
    parser.add_argument("--projector-radial-k1", type=float, default=0.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = IdealDatasetConfig(
        width=args.width,
        height=args.height,
        seed=args.seed,
        projector_period_px=args.projector_period_px,
        height_shift_px_per_mm=args.height_shift_px_per_mm,
        board_profile=args.board_profile,
        projector_radial_k1=args.projector_radial_k1,
    )
    output = generate_ideal_dataset(args.output_root, config)
    print(f"Generated ideal dataset: {output}")
    print("Views: object_0, object_180, reference_0, reference_180 (22 frames each)")
    print(f"Manifest: {output / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
