from __future__ import annotations

import numpy as np
from PIL import Image

from pcb_fpp_decoder.io import read_image_gray


def test_read_mono16_normalizes_to_decoder_8bit_domain(tmp_path) -> None:
    source = np.array([[0, 32768, 65535]], dtype=np.uint16)
    path = tmp_path / "mono16.png"
    Image.fromarray(source, mode="I;16").save(path)

    result = read_image_gray(path, color_mode="smartphone_uv_blue")

    assert result.dtype == np.float32
    np.testing.assert_allclose(result, [[0.0, 127.50195, 255.0]], atol=1e-3)
