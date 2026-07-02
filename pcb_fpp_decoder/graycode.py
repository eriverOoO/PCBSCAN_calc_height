from __future__ import annotations

import numpy as np


def gray_to_binary(gray: np.ndarray | int, bits: int = 8) -> np.ndarray | int:
    """Convert Gray-code integers to binary integers.

    The implementation uses a vectorized prefix-xor sequence for ndarray input
    and the same logic for scalar integers.
    """
    if bits <= 0:
        raise ValueError("bits must be positive")

    if np.isscalar(gray):
        value = int(gray)
        shift = 1
        while shift < bits:
            value ^= value >> shift
            shift <<= 1
        return value

    binary = np.asarray(gray).copy()
    if not np.issubdtype(binary.dtype, np.integer):
        binary = binary.astype(np.uint32)

    shift = 1
    while shift < bits:
        binary = np.bitwise_xor(binary, np.right_shift(binary, shift))
        shift <<= 1
    return binary


def bits_to_integer(bits_array: np.ndarray) -> np.ndarray:
    """Pack MSB-first bit planes into an integer image."""
    if bits_array.ndim < 1:
        raise ValueError("bits_array must have at least one dimension")
    bit_count = bits_array.shape[-1]
    weights = (1 << np.arange(bit_count - 1, -1, -1, dtype=np.uint32))
    return np.tensordot(bits_array.astype(np.uint32), weights, axes=([-1], [0])).astype(
        np.uint32
    )


def decode_gray_bits(gray_bit_planes: np.ndarray, bits: int = 8) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(gray_value, binary_value)`` from MSB-first Gray-code bit planes."""
    if gray_bit_planes.shape[-1] != bits:
        raise ValueError(
            f"expected {bits} Gray-code bit planes, got {gray_bit_planes.shape[-1]}"
        )
    gray_value = bits_to_integer(gray_bit_planes)
    binary_value = gray_to_binary(gray_value, bits=bits).astype(np.uint32)
    return gray_value, binary_value
