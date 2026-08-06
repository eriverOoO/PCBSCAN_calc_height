from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pcb_fpp_decoder.capture_contract import write_capture_contract_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify hardware-trigger and fixed-camera evidence in scan_log.json."
    )
    parser.add_argument("--input", required=True, type=Path, help="Captured pattern folder")
    parser.add_argument(
        "--output",
        type=Path,
        help="JSON report path (default: <input>/hardware_capture_report.json)",
    )
    args = parser.parse_args(argv)
    output = args.output or args.input / "hardware_capture_report.json"
    report = write_capture_contract_report(args.input, output)
    print(f"Hardware capture audit: {report['status']}")
    print(f"Report: {output}")
    for error in report["errors"]:
        print(f"ERROR: {error}")
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
