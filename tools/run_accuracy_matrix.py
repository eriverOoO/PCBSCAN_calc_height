from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validation_harness.runner import ValidationRunner
from validation_harness.l0 import run_l0_validation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Decode L0/L1 cases, then evaluate isolated GT after decoding"
    )
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--level", choices=("auto", "l0", "l1"), default="auto")
    parser.add_argument("--seed", type=int, default=0, help="L0 generator seed")
    parser.add_argument("--generator-commit", default="unknown", help="L0 generator commit/hash")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.dataset_root.expanduser().resolve()
    if args.level == "l0" or (
        args.level == "auto" and (root / "pattern_000.png").exists()
    ):
        run_l0_validation(
            root,
            args.output_root,
            seed=args.seed,
            generator_commit=args.generator_commit,
        )
        print(f"L0 self-consistency report: {args.output_root / 'summary.json'}")
        return 0
    cases = sorted(path for path in root.glob("case_*") if path.is_dir())
    if not cases and (root / "views").is_dir():
        cases = [root]
    if not cases:
        raise SystemExit(f"No validation case found below {root}")
    for case in cases:
        result_dir = args.output_root / case.name
        ValidationRunner().run_case(case, result_dir)
        print(f"Evaluated {case.name}: {result_dir / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
