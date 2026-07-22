from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validation_harness.dashboard import write_suite_dashboard
from validation_harness.ideal import (
    BOARD_PROFILE_METADATA,
    IdealDatasetConfig,
    generate_ideal_dataset,
)
from validation_harness.l0 import run_l0_validation
from validation_harness.manifests import inspect_pattern_sequence, load_config
from validation_harness.runner import ValidationRunner
from validation_harness.stress import generate_stress_case


REFERENCE_BOARDS = (
    "adafruit_bme280",
    "soldered_simple_light",
    "soldered_w5500",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate and compare source-informed open-hardware PCB simulations"
    )
    parser.add_argument(
        "--ideal-root",
        type=Path,
        default=Path("validation_data/ideal/open_hardware_boards"),
    )
    parser.add_argument(
        "--stress-root",
        type=Path,
        default=Path("validation_data/stress/held_out/open_hardware_boards"),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("validation_results/open_hardware_boards"),
    )
    parser.add_argument("--boards", nargs="+", choices=REFERENCE_BOARDS, default=list(REFERENCE_BOARDS))
    parser.add_argument("--stress-profile", choices=("clean", "normal", "hard", "extreme"), default="normal")
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=320)
    parser.add_argument("--seed", type=int, default=41)
    parser.add_argument("--open", action="store_true", dest="open_dashboard")
    return parser


def _dataset_matches(dataset_root: Path, board_profile: str) -> bool:
    manifest_path = dataset_root / "manifest.json"
    if not manifest_path.exists():
        return False
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return manifest.get("generator", {}).get("config", {}).get("board_profile") == board_profile


def run_reference_suite(args: argparse.Namespace) -> tuple[Path, list[dict[str, Any]]]:
    workspace = Path(__file__).resolve().parents[1]
    ideal_root = args.ideal_root.expanduser().resolve()
    stress_root = args.stress_root.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    profile_path = workspace / "configs" / f"validation_l1_{args.stress_profile}.yaml"
    stress_profile = load_config(profile_path)
    base_seed = int(stress_profile["quick_seeds"][0])
    cases: list[dict[str, Any]] = []
    l0_checks: dict[str, Any] = {}

    for index, board_profile in enumerate(args.boards):
        dataset_root = ideal_root / board_profile
        case_seed = base_seed + index
        case_dir = stress_root / board_profile / f"case_{case_seed}"
        result_dir = output_root / board_profile / f"case_{case_seed}"
        print(f"[{board_profile}] ideal + L0 + L1:{args.stress_profile}")
        record: dict[str, Any] = {
            "profile": board_profile,
            "seed": case_seed,
            "case_dir": str(case_dir),
            "result_dir": str(result_dir),
            "status": "error",
        }
        try:
            if dataset_root.exists():
                if not _dataset_matches(dataset_root, board_profile):
                    raise ValueError(f"existing dataset profile mismatch: {dataset_root}")
            else:
                generate_ideal_dataset(
                    dataset_root,
                    IdealDatasetConfig(
                        width=args.width,
                        height=args.height,
                        seed=args.seed + index,
                        board_profile=board_profile,
                        projector_radial_k1=-0.018,
                        projector_optical_axis_offset_px=(4.0, -3.0),
                    ),
                )
            for view in ("object_0", "object_180", "reference_0", "reference_180"):
                inspect_pattern_sequence(dataset_root / view)
            l0 = run_l0_validation(
                dataset_root / "object_0",
                output_root / "l0" / board_profile,
                seed=args.seed + index,
                generator_commit="working-tree",
            )
            l0_checks[board_profile] = l0.get("checks", {})
            if not case_dir.exists():
                generate_stress_case(
                    input_root=dataset_root,
                    output_root=stress_root / board_profile,
                    profile_path=profile_path,
                    seed=case_seed,
                    partition="held_out",
                )
            summary = ValidationRunner().run_case(case_dir, result_dir)
            record["summary"] = summary
            record["status"] = "ok"
        except Exception as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
            print(f"  ERROR: {record['error']}")
        cases.append(record)

    metadata = {
        "board_profiles": list(args.boards),
        "board_sources": {name: BOARD_PROFILE_METADATA[name] for name in args.boards},
        "stress_profile": args.stress_profile,
        "scanner_sim_adaptations": [
            "independent camera/projector model",
            "explicit projector optical axis and radial distortion",
            "focus/radiometric effects evaluated in L1",
            "ground truth isolated from decoder inputs",
        ],
        "phase_domain_only": True,
    }
    dashboard, _ = write_suite_dashboard(
        output_root,
        cases=cases,
        l0_summary={"checks": l0_checks},
        suite_metadata=metadata,
    )
    return dashboard, cases


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    dashboard, cases = run_reference_suite(args)
    failures = sum(case["status"] != "ok" for case in cases)
    print(f"Dashboard: {dashboard}")
    print(f"Boards: {len(cases) - failures}/{len(cases)} completed")
    if args.open_dashboard:
        if hasattr(os, "startfile"):
            os.startfile(dashboard)  # type: ignore[attr-defined]
        else:
            import webbrowser

            webbrowser.open(dashboard.as_uri())
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
