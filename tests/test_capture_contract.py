import json
from pathlib import Path

from pcb_fpp_decoder.capture_contract import audit_capture_contract
from pcb_fpp_decoder.cli import main as cli_main


def _strict_log(angle: int | None = None) -> dict:
    payload = {
        "capture_contract_version": 1,
        "scan_id": "strict-test",
        "status": "ok",
        "capture_protocol": {
            "sequence_locked": True,
            "projector_pattern_advance": "hardware_trigger",
            "camera_exposure": "hardware_trigger",
            "trigger_source": "PRO4500.TRIG_OUT -> XIMEA.GPI_1",
        },
        "settings": {
            "auto_exposure": False,
            "auto_gain": False,
            "auto_white_balance": False,
            "gamma_enabled": False,
            "output_linear": True,
            "exposure_mode": "manual",
            "gain_mode": "manual",
            "focus_mode": "manual",
            "pixel_format": "Mono8",
        },
        "rows": [
            {
                "pattern_id": pattern_id,
                "filename": f"pattern_{pattern_id:03d}.png",
                "sequence_index": pattern_id,
                "trigger_id": f"trigger-{pattern_id:03d}",
            }
            for pattern_id in range(14)
        ],
    }
    if angle is not None:
        payload["stage"] = {
            "position_id": f"deg_{angle}",
            "commanded_angle_deg": float(angle),
            "actual_angle_deg": float(angle) + 0.08,
            "settled": True,
        }
    return payload


def test_strict_hardware_capture_contract_accepts_complete_evidence(tmp_path: Path):
    (tmp_path / "scan_log.json").write_text(json.dumps(_strict_log()), encoding="utf-8")

    report = audit_capture_contract(tmp_path)

    assert report["status"] == "passed"
    assert report["errors"] == []


def test_strict_hardware_capture_contract_rejects_auto_gamma_and_missing_trigger(tmp_path: Path):
    log = _strict_log()
    log["settings"]["gamma_enabled"] = True
    del log["rows"][3]["trigger_id"]
    (tmp_path / "scan_log.json").write_text(json.dumps(log), encoding="utf-8")

    report = audit_capture_contract(tmp_path)

    assert report["status"] == "rejected"
    assert any("gamma_enabled" in error for error in report["errors"])
    assert any("trigger_id" in error for error in report["errors"])


def test_cli_strict_mode_rejects_capture_without_contract(tmp_path: Path):
    input_dir = tmp_path / "capture"
    output_dir = tmp_path / "processed"
    input_dir.mkdir()

    try:
        cli_main(
            [
                "--input",
                str(input_dir),
                "--output",
                str(output_dir),
                "--require-hardware-capture",
            ]
        )
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("strict CLI mode should reject an unproven capture")


def test_four_direction_contract_accepts_settled_stage_angle(tmp_path: Path):
    (tmp_path / "scan_log.json").write_text(json.dumps(_strict_log(90)), encoding="utf-8")

    report = audit_capture_contract(tmp_path, expected_view_angle_deg=90)

    assert report["status"] == "passed"
    assert report["evidence"]["stage"]["position_id"] == "deg_90"


def test_four_direction_contract_rejects_wrong_or_unsettled_angle(tmp_path: Path):
    log = _strict_log(90)
    log["stage"]["actual_angle_deg"] = 88.9
    log["stage"]["settled"] = False
    (tmp_path / "scan_log.json").write_text(json.dumps(log), encoding="utf-8")

    report = audit_capture_contract(
        tmp_path,
        expected_view_angle_deg=90,
        stage_angle_tolerance_deg=0.5,
    )

    assert report["status"] == "rejected"
    assert any("settled" in error for error in report["errors"])
    assert any("actual angle" in error for error in report["errors"])
