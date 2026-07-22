from __future__ import annotations

import argparse
from pathlib import Path

from tools.run_reference_board_suite import run_reference_suite


def test_reference_board_suite_creates_visual_comparison(tmp_path: Path) -> None:
    args = argparse.Namespace(
        ideal_root=tmp_path / "ideal",
        stress_root=tmp_path / "stress",
        output_root=tmp_path / "results",
        boards=["adafruit_bme280"],
        stress_profile="clean",
        width=96,
        height=64,
        seed=41,
        open_dashboard=False,
    )
    dashboard, cases = run_reference_suite(args)
    assert cases[0]["status"] == "ok"
    assert "adafruit_bme280" in dashboard.read_text(encoding="utf-8")
    assert (
        tmp_path
        / "results"
        / "assets"
        / "adafruit_bme280_2000"
        / "input_object_0.png"
    ).exists()
