import numpy as np

from pcb_fpp_decoder.graycode import decode_gray_bits, gray_to_binary


def binary_to_gray(value: int) -> int:
    return value ^ (value >> 1)


def test_gray_to_binary_scalar_and_vector():
    values = np.arange(256, dtype=np.uint16)
    gray = values ^ (values >> 1)
    decoded = gray_to_binary(gray, bits=8)
    np.testing.assert_array_equal(decoded, values)
    assert gray_to_binary(binary_to_gray(173), bits=8) == 173


def test_decode_gray_bits_msb_first():
    values = np.array([0, 1, 2, 7, 128, 255], dtype=np.uint16)
    gray = values ^ (values >> 1)
    bits = ((gray[:, None] >> np.arange(7, -1, -1)) & 1).astype(np.uint8)
    gray_value, decoded = decode_gray_bits(bits, bits=8)
    np.testing.assert_array_equal(gray_value, gray)
    np.testing.assert_array_equal(decoded, values)
