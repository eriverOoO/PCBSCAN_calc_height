from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from pcb_fpp_decoder.decoder import DecodeConfig, PcbFppDecoder
from pcb_fpp_decoder.validation import accuracy_metrics


DATASET = Path(
    r"C:\Users\LEELAB\Desktop\PRO4500_CONTROL_ximea\synthetic_pcb_structured_light"
)


@pytest.mark.skipif(not DATASET.exists(), reason="bundled synthetic dataset is unavailable")
def test_provided_synthetic_phase_linear_fusion(tmp_path):
    output = DATASET / "output"
    config = DecodeConfig(
        height_mode="phase_linear",
        reference_scan_0=output / "reference" / "angle_000",
        reference_scan_180=output / "reference" / "angle_180",
        calibration_config=DATASET / "configs" / "synthetic_decoder_calibration.json",
        phase_convention="swapped",
        min_signal=5.0,
        median_filter=3,
        detrend=False,
        fusion_max_height_difference_mm=0.25,
        output_profile="compact",
    )
    fusion = PcbFppDecoder(config).decode_fused(
        output / "angle_000", output / "angle_180", tmp_path / "decoded"
    )

    # Ground truth is loaded only after the ordinary decode call has returned.
    truth = np.load(output / "ground_truth" / "angle_000_height_mm.npy")
    pcb = np.asarray(Image.open(output / "ground_truth" / "valid_mask.png")) > 0
    overall = accuracy_metrics(fusion.height.height, truth, pcb)
    tall = accuracy_metrics(fusion.height.height, truth, pcb & (truth >= 1.0))

    assert fusion.height.metric is True
    assert fusion.height.units == "mm"
    assert np.nanmedian(fusion.height.height[pcb & (truth >= 1.0)]) > 1.0
    assert overall["valid_ratio"] >= 0.99
    assert tall["valid_ratio"] >= 0.98
    assert overall["p95_absolute_error_mm"] <= 0.05
    assert overall["rmse_mm"] <= 0.10
    assert (tmp_path / "decoded" / "masks" / "cycle_slip_mask.png").exists()
    assert (tmp_path / "decoded" / "masks" / "fusion_rejection_mask.png").exists()
