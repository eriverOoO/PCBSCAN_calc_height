import numpy as np

from pcb_fpp_decoder.phase import (
    TWO_PI,
    compute_wrapped_phase_4step,
    diagnose_phase_conventions,
    wrapped_to_0_2pi,
)


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


def test_cosine_phase_diagnosis_recommends_swapped():
    phi = np.linspace(0, 4 * np.pi, 64, dtype=np.float32)[None, :]
    phi = np.repeat(phi, 4, axis=0)
    mean = 100.0
    amp = 30.0
    result = diagnose_phase_conventions(
        mean + amp * np.cos(phi),
        mean - amp * np.sin(phi),
        mean - amp * np.cos(phi),
        mean + amp * np.sin(phi),
    )

    assert result["recommended"] == "swapped"
    assert result["scores"]["swapped"] > 0.999


def test_wrapped_phase_stabilizes_values_near_two_pi_to_zero():
    wrapped = np.array([-1e-8, 0.0, TWO_PI - 1e-8], dtype=np.float64)
    converted = wrapped_to_0_2pi(wrapped)
    np.testing.assert_array_equal(converted, np.zeros(3, dtype=np.float32))
