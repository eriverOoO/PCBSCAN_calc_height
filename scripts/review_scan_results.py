from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pcb_fpp_decoder.capture_contract import audit_capture_contract


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def build_review(capture_dir: Path, processed_dir: Path) -> dict[str, Any]:
    capture_dir = capture_dir.expanduser().resolve()
    processed_dir = processed_dir.expanduser().resolve()
    contract = audit_capture_contract(capture_dir)
    decode_report = _read_json(processed_dir / "decode_report.json")
    diagnosis_path = processed_dir / "capture_diagnosis.txt"
    diagnosis = diagnosis_path.read_text(encoding="utf-8-sig") if diagnosis_path.is_file() else None

    findings: list[str] = []
    if contract["status"] != "passed":
        findings.append("Capture provenance is incomplete; do not make a metric-accuracy claim.")
    if decode_report is None:
        findings.append("decode_report.json is missing from the processed folder.")
    else:
        coverage = decode_report.get("mask_coverage")
        if isinstance(coverage, dict):
            ratio = coverage.get("combined_mask_ratio")
            if isinstance(ratio, (int, float)) and ratio < 0.9:
                findings.append(f"Combined valid-pixel ratio is low ({ratio:.1%}); inspect glare, focus, and pattern order.")
        capture = decode_report.get("phone_capture")
        if isinstance(capture, dict):
            for warning in capture.get("warnings", []):
                if isinstance(warning, str):
                    findings.append(warning)
    if diagnosis is None:
        findings.append("capture_diagnosis.txt is missing; rerun the decoder before review.")

    return {
        "capture_dir": str(capture_dir),
        "processed_dir": str(processed_dir),
        "capture_contract": contract,
        "decode_report": decode_report,
        "capture_diagnosis": diagnosis,
        "findings": list(dict.fromkeys(findings)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Package a capture folder and its processed result for a repeatable scan review."
    )
    parser.add_argument("--capture", required=True, type=Path)
    parser.add_argument("--processed", required=True, type=Path)
    parser.add_argument("--output", type=Path, help="Default: <processed>/scan_review.json")
    args = parser.parse_args(argv)
    output = args.output or args.processed / "scan_review.json"
    report = build_review(args.capture, args.processed)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Scan review: {output}")
    print(f"Capture contract: {report['capture_contract']['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
