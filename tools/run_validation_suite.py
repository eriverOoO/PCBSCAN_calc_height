from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validation_harness.dashboard import write_suite_dashboard
from validation_harness.ideal import IdealDatasetConfig, generate_ideal_dataset
from validation_harness.l0 import run_l0_validation
from validation_harness.manifests import inspect_pattern_sequence, load_config
from validation_harness.runner import ValidationRunner
from validation_harness.stress import generate_stress_case


PROFILE_NAMES = ("clean", "normal", "hard", "extreme", "cs126mu", "source_empirical")
DEFAULT_PROFILE_NAMES = ("clean", "normal", "hard", "extreme", "cs126mu")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run ideal generation, L0, L1 profile matrix and one-page dashboard"
    )
    parser.add_argument(
        "--ideal-root",
        type=Path,
        default=Path("validation_data/ideal/procedural_pcb_v2"),
    )
    parser.add_argument(
        "--stress-root",
        type=Path,
        default=Path("validation_data/stress/held_out/automated_suite_v2"),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("validation_results/automated_suite_v2"),
    )
    parser.add_argument(
        "--profiles", nargs="+", choices=PROFILE_NAMES, default=list(DEFAULT_PROFILE_NAMES)
    )
    parser.add_argument("--seeds-per-profile", type=int, choices=(1, 2), default=1)
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=320)
    parser.add_argument("--ideal-seed", type=int, default=17)
    parser.add_argument("--open", action="store_true", dest="open_dashboard")
    return parser


def _git_head(workspace: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=workspace,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except Exception:
        return "working-tree"


def _case_matches_profile(case_dir: Path, profile_name: str) -> bool:
    manifest_path = case_dir / "manifest.json"
    if not manifest_path.exists():
        return False
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return manifest.get("profile", {}).get("profile") == profile_name


def run_suite(args: argparse.Namespace) -> tuple[Path, list[dict[str, Any]]]:
    workspace = Path(__file__).resolve().parents[1]
    ideal_root = args.ideal_root.expanduser().resolve()
    stress_root = args.stress_root.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()

    if not ideal_root.exists():
        print(f"[ideal] generating {args.width}x{args.height}: {ideal_root}")
        generate_ideal_dataset(
            ideal_root,
            IdealDatasetConfig(
                width=args.width,
                height=args.height,
                seed=args.ideal_seed,
            ),
        )
    for view in ("object_0", "object_180", "reference_0", "reference_180"):
        inspect_pattern_sequence(ideal_root / view)

    print("[L0] self-consistency")
    l0_summary = run_l0_validation(
        ideal_root / "object_0",
        output_root / "l0",
        seed=args.ideal_seed,
        generator_commit=_git_head(workspace),
    )

    cases: list[dict[str, Any]] = []
    for profile_name in args.profiles:
        profile_path = workspace / "configs" / f"validation_l1_{profile_name}.yaml"
        profile = load_config(profile_path)
        seeds = [int(seed) for seed in profile["quick_seeds"][: args.seeds_per_profile]]
        for seed in seeds:
            case_dir = stress_root / profile_name / f"case_{seed}"
            result_dir = output_root / profile_name / f"case_{seed}"
            print(f"[L1:{profile_name}] seed={seed}")
            record: dict[str, Any] = {
                "profile": profile_name,
                "seed": seed,
                "case_dir": str(case_dir),
                "result_dir": str(result_dir),
                "status": "error",
            }
            try:
                if case_dir.exists():
                    if not _case_matches_profile(case_dir, profile_name):
                        raise ValueError(
                            f"existing case profile mismatch: {case_dir}; use another --stress-root"
                        )
                else:
                    generate_stress_case(
                        input_root=ideal_root,
                        output_root=stress_root / profile_name,
                        profile_path=profile_path,
                        seed=seed,
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
        "profiles": list(args.profiles),
        "seeds_per_profile": args.seeds_per_profile,
        "ideal_root": str(ideal_root),
        "stress_root": str(stress_root),
        "phase_domain_only": True,
    }
    dashboard_path, _json_path = write_suite_dashboard(
        output_root,
        cases=cases,
        l0_summary=l0_summary,
        suite_metadata=metadata,
    )
    return dashboard_path, cases


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    dashboard, cases = run_suite(args)
    failures = sum(case["status"] != "ok" for case in cases)
    print(f"Dashboard: {dashboard}")
    print(f"Cases: {len(cases) - failures}/{len(cases)} completed")
    if args.open_dashboard:
        if hasattr(os, "startfile"):
            os.startfile(dashboard)  # type: ignore[attr-defined]
        else:
            import webbrowser

            webbrowser.open(dashboard.as_uri())
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
