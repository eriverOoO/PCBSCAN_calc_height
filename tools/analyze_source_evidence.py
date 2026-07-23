from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validation_harness.evidence import write_source_evidence_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare checksum-pinned physical scanner-sim HDR samples with a local "
            "synthetic 22-pattern sequence without treating either as hardware accuracy"
        )
    )
    parser.add_argument(
        "--scanner-root",
        type=Path,
        default=Path("validation_data/external/scanner_sim_physical"),
    )
    parser.add_argument(
        "--synthetic-root",
        type=Path,
        default=Path("validation_data/ideal/source_grounded_pcb_v2"),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("validation_results/source_grounded/evidence"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    html_path, json_path = write_source_evidence_report(
        args.scanner_root, args.synthetic_root, args.output_root
    )
    print(f"Source evidence HTML: {html_path}")
    print(f"Source evidence JSON: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
