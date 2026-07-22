from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.run_validation_suite import run_suite


def test_one_command_suite_creates_dashboard_and_reuses_case(tmp_path: Path) -> None:
    args = argparse.Namespace(
        ideal_root=tmp_path / "ideal",
        stress_root=tmp_path / "stress",
        output_root=tmp_path / "results",
        profiles=["clean"],
        seeds_per_profile=1,
        width=96,
        height=64,
        ideal_seed=17,
        open_dashboard=False,
    )
    dashboard, cases = run_suite(args)
    assert dashboard.exists()
    assert cases[0]["status"] == "ok"
    dashboard_text = dashboard.read_text(encoding="utf-8")
    assert "Case별 입력과 결과" in dashboard_text
    assert "4개 view의 입력 88장 보기" in dashboard_text
    assert (tmp_path / "results" / "assets" / "clean_2000" / "input_object_0.png").exists()
    payload = json.loads((tmp_path / "results" / "suite_summary.json").read_text())
    assert payload["failure_count"] == 0
    assert payload["schema_version"] == 2
    assert payload["profiles"][0]["profile"] == "clean"

    second_dashboard, second_cases = run_suite(args)
    assert second_dashboard == dashboard
    assert second_cases[0]["status"] == "ok"
