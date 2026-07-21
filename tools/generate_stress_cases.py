from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validation_harness.stress import generate_stress_case


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a deterministic L1 stress case without modifying the ideal input"
    )
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument(
        "--partition", choices=("calibration", "held_out"), default="held_out"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    case = generate_stress_case(
        input_root=args.input_root,
        output_root=args.output_root,
        profile_path=args.profile,
        seed=args.seed,
        partition=args.partition,
    )
    print(f"Generated deterministic stress case: {case}")
    print(f"Manifest: {case / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
