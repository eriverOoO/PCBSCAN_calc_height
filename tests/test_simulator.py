from pcb_fpp_decoder.simulator import PcbFppSimulator, SyntheticPcbConfig


def test_virtual_pcb_simulator_reports_small_clean_error(tmp_path):
    config = SyntheticPcbConfig(
        width=96,
        height=64,
        stripe_width_px=5.0,
        height_scale=1.0,
        include_inverted_gray=True,
        add_defects=False,
        noise_sigma=0.0,
        blur_sigma=0.0,
        median_filter=0,
        max_point_cloud_points=20_000,
    )

    result = PcbFppSimulator(config).run(tmp_path / "simulation")
    report = result.report

    assert (result.output_root / "simulation_report.json").exists()
    assert (result.object_scan_dir / "pattern_000.png").exists()
    assert (result.truth_dir / "height_true.npy").exists()
    assert (result.output_root / "accuracy" / "height_error.npy").exists()
    assert report["metrics"]["stripe_order"]["exact_ratio"] == 1.0
    assert report["metrics"]["height"]["rmse"] < 0.02
    assert report["coverage"]["decoded_over_truth_ratio"] > 0.99
