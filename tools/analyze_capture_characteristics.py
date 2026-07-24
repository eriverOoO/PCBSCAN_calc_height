from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validation_harness.capture_evidence import (
    SUPPORTED_SUFFIXES,
    write_capture_evidence_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit unordered real camera captures for observable image-domain "
            "characteristics without treating them as phase/height ground truth"
        )
    )
    parser.add_argument(
        "--capture-root",
        type=Path,
        default=Path("validation_data/external/ximea_0724"),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("validation_results/ximea_observed/evidence"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.capture_root.expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"capture root not found: {root}")
    paths = sorted(
        (
            path
            for path in root.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
        ),
        key=lambda path: path.name.lower(),
    )
    html_path, json_path, contact_sheet = write_capture_evidence_report(
        paths, args.output_root
    )
    print(f"Capture evidence HTML: {html_path}")
    print(f"Capture evidence JSON: {json_path}")
    print(f"Capture contact sheet: {contact_sheet}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
