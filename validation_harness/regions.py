from __future__ import annotations

from typing import Mapping

import numpy as np


REGION_NAMES = (
    "pcb_all",
    "flat_substrate",
    "components_all",
    "components_ge_1mm",
    "low_reflectance",
    "high_reflectance_or_saturated",
    "shadow",
    "gray_boundary",
    "injected_hot_pixel",
    "injected_bit_flip",
    "injected_cycle_slip",
    "view_overlap",
    "single_view",
)


def _mask(value: np.ndarray | None, shape: tuple[int, ...]) -> np.ndarray:
    if value is None:
        return np.zeros(shape, dtype=bool)
    result = np.asarray(value, dtype=bool)
    if result.shape != shape:
        raise ValueError(f"region mask has shape {result.shape}; expected {shape}")
    return result


def build_region_masks(
    shape: tuple[int, ...],
    *,
    object_mask: np.ndarray | None = None,
    material_id: np.ndarray | None = None,
    height_gt: np.ndarray | None = None,
    impairment_masks: Mapping[str, np.ndarray] | None = None,
    view_valid_masks: tuple[np.ndarray, np.ndarray] | None = None,
) -> dict[str, np.ndarray]:
    impairments = impairment_masks or {}
    pcb = _mask(object_mask, shape) if object_mask is not None else np.ones(shape, dtype=bool)
    materials = np.asarray(material_id) if material_id is not None else np.zeros(shape, dtype=np.uint8)
    if materials.shape != shape:
        raise ValueError("material_id shape mismatch")
    height = np.asarray(height_gt) if height_gt is not None else np.zeros(shape, dtype=float)
    if height.shape != shape:
        raise ValueError("height_gt shape mismatch")

    masks = {
        "pcb_all": pcb,
        "flat_substrate": pcb & (np.abs(height) < 1e-6),
        "components_all": pcb & (height > 0),
        "components_ge_1mm": pcb & (height >= 1.0),
        "low_reflectance": pcb & np.isin(materials, [4]),
        "high_reflectance_or_saturated": pcb
        & (np.isin(materials, [2, 3, 5]) | _mask(impairments.get("saturation"), shape)),
        "shadow": pcb & _mask(impairments.get("shadow"), shape),
        "gray_boundary": pcb & _mask(impairments.get("gray_boundary"), shape),
        "injected_hot_pixel": pcb & _mask(impairments.get("hot_pixel"), shape),
        "injected_bit_flip": pcb & _mask(impairments.get("bit_flip"), shape),
        "injected_cycle_slip": pcb & _mask(impairments.get("cycle_slip"), shape),
    }
    if view_valid_masks is None:
        masks["view_overlap"] = np.zeros(shape, dtype=bool)
        masks["single_view"] = np.zeros(shape, dtype=bool)
    else:
        deg0 = _mask(view_valid_masks[0], shape)
        deg180 = _mask(view_valid_masks[1], shape)
        masks["view_overlap"] = pcb & deg0 & deg180
        masks["single_view"] = pcb & np.logical_xor(deg0, deg180)
    return masks
