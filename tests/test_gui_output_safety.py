import json

from pcb_fpp_decoder.gui import (
    is_default_scan_output_dir,
    output_matches_input_scan,
    suggested_output_dir,
)


def test_default_output_directory_tracks_scan_id(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)

    assert suggested_output_dir(tmp_path / "scan_20260804_164300") == (
        tmp_path / "processed" / "scan_20260804_164300"
    )
    assert is_default_scan_output_dir(tmp_path / "processed" / "scan_20260804_155320")
    assert not is_default_scan_output_dir(tmp_path / "custom-results")


def test_existing_output_report_must_match_selected_input(tmp_path) -> None:
    old_input = tmp_path / "captures" / "scan_old" / "angle_000"
    new_input = tmp_path / "captures" / "scan_new" / "angle_000"
    output = tmp_path / "processed" / "scan_old"
    output.mkdir(parents=True)
    (output / "decode_report.json").write_text(
        json.dumps({"input_dir": str(old_input)}), encoding="utf-8"
    )

    assert output_matches_input_scan(output, old_input)
    assert not output_matches_input_scan(output, new_input)
