import numpy as np

from pcb_fpp_decoder.phase import compute_wrapped_phase_4step


def test_4step_wrapped_phase_default_convention():
    phi = np.linspace(-np.pi, np.pi, 257, dtype=np.float32)
    mean = 100.0
    amp = 35.0
    i0 = mean + amp * np.sin(phi)
    i180 = mean - amp * np.sin(phi)
    i270 = mean + amp * np.cos(phi)
    i90 = mean - amp * np.cos(phi)

    decoded = compute_wrapped_phase_4step(i0, i90, i180, i270)
    error = np.angle(np.exp(1j * (decoded - phi)))
    assert np.max(np.abs(error)) < 1e-6
