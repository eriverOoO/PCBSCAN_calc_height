from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .manifests import output_hashes, sha256_file, write_json


VIEW_NAMES = ("object_0", "object_180", "reference_0", "reference_180")


@dataclass(frozen=True)
class IdealDatasetConfig:
    width: int = 512
    height: int = 320
    seed: int = 17
    projector_period_px: float = 24.0
    projector_skew_px_per_row: float = 0.035
    height_shift_px_per_mm: float = 1.8
    black_level: float = 3500.0
    signal_level: float = 54000.0
    sine_contrast: float = 0.45

    def validate(self) -> None:
        if self.width < 64 or self.height < 48:
            raise ValueError("ideal dataset must be at least 64x48 pixels")
        if self.projector_period_px <= 2:
            raise ValueError("projector_period_px must be greater than 2")
        if not 0.0 < self.sine_contrast <= 0.5:
            raise ValueError("sine_contrast must be in (0, 0.5]")
        if self.black_level < 0 or self.signal_level <= 0:
            raise ValueError("radiometric levels must be non-negative")
        if self.black_level + self.signal_level > 65535:
            raise ValueError("black_level + signal_level must fit uint16")


@dataclass(frozen=True)
class SceneMaps:
    height_mm: np.ndarray
    albedo: np.ndarray
    material_id: np.ndarray
    object_mask: np.ndarray
    flat_substrate_mask: np.ndarray
    component_mask: np.ndarray


def _rounded_rect(
    xx: np.ndarray,
    yy: np.ndarray,
    *,
    center_x: float,
    center_y: float,
    half_width: float,
    half_height: float,
    radius: float,
) -> np.ndarray:
    dx = np.maximum(np.abs(xx - center_x) - (half_width - radius), 0.0)
    dy = np.maximum(np.abs(yy - center_y) - (half_height - radius), 0.0)
    return dx * dx + dy * dy <= radius * radius


def _rect(
    xx: np.ndarray,
    yy: np.ndarray,
    center_x: float,
    center_y: float,
    half_width: float,
    half_height: float,
) -> np.ndarray:
    return (np.abs(xx - center_x) <= half_width) & (
        np.abs(yy - center_y) <= half_height
    )


def _build_object_scene(config: IdealDatasetConfig) -> SceneMaps:
    height, width = config.height, config.width
    rng = np.random.default_rng(config.seed)
    yy, xx = np.indices((height, width), dtype=np.float32)
    cx = (width - 1) / 2.0
    cy = (height - 1) / 2.0
    board = _rounded_rect(
        xx,
        yy,
        center_x=cx,
        center_y=cy,
        half_width=width * 0.34,
        half_height=height * 0.36,
        radius=min(width, height) * 0.035,
    )

    height_mm = np.zeros((height, width), dtype=np.float32)
    material_id = np.zeros((height, width), dtype=np.uint8)
    albedo = np.full((height, width), 0.72, dtype=np.float32)
    material_id[board] = 1  # solder mask/substrate
    texture_phase_x, texture_phase_y = rng.uniform(0.0, 2.0 * np.pi, size=2)
    board_texture = 0.012 * np.sin(xx / 19.0 + texture_phase_x) * np.cos(
        yy / 23.0 + texture_phase_y
    )
    albedo[board] = 0.46 + board_texture[board]

    # A deterministic assortment of actual mesh-like PCB regions: large IC,
    # connector, ceramic passives, exposed pads and solder joints.
    ic = _rect(xx, yy, cx - width * 0.08, cy, width * 0.075, height * 0.10) & board
    height_mm[ic] = 2.1
    material_id[ic] = 4
    albedo[ic] = 0.14

    connector = _rect(
        xx, yy, cx + width * 0.22, cy - height * 0.17, width * 0.07, height * 0.11
    ) & board
    height_mm[connector] = 3.2
    material_id[connector] = 7
    albedo[connector] = 0.28

    ceramic = np.zeros((height, width), dtype=bool)
    for offset_x, offset_y in (
        (-0.24, -0.20),
        (-0.17, -0.20),
        (-0.24, 0.22),
        (-0.17, 0.22),
        (0.10, 0.20),
        (0.18, 0.20),
    ):
        ceramic |= _rect(
            xx,
            yy,
            cx + width * offset_x,
            cy + height * offset_y,
            width * 0.022,
            height * 0.025,
        )
    ceramic &= board
    height_mm[ceramic] = 1.15
    material_id[ceramic] = 6
    albedo[ceramic] = 0.72

    pads = np.zeros((height, width), dtype=bool)
    for index in range(8):
        pads |= _rect(
            xx,
            yy,
            cx - width * 0.11 + index * width * 0.032,
            cy + height * 0.31,
            width * 0.010,
            height * 0.025,
        )
    for index in range(5):
        pads |= _rect(
            xx,
            yy,
            cx + width * 0.29,
            cy - height * 0.04 + index * height * 0.045,
            width * 0.014,
            height * 0.014,
        )
    pads &= board
    height_mm[pads] = np.maximum(height_mm[pads], 0.18)
    material_id[pads] = 2
    albedo[pads] = 0.92

    solder = np.zeros((height, width), dtype=bool)
    for center_dx, center_dy in ((0.08, -0.18), (0.14, -0.18), (0.20, -0.18)):
        radius = min(width, height) * 0.023
        solder |= (
            (xx - (cx + width * center_dx)) ** 2
            + (yy - (cy + height * center_dy)) ** 2
            <= radius**2
        )
    solder &= board
    height_mm[solder] = 0.65
    material_id[solder] = 3
    albedo[solder] = 0.84

    components = board & (height_mm > 0)
    return SceneMaps(
        height_mm=height_mm,
        albedo=albedo,
        material_id=material_id,
        object_mask=board,
        flat_substrate_mask=board & ~components,
        component_mask=components,
    )


def _rotate_scene(scene: SceneMaps) -> SceneMaps:
    return SceneMaps(
        height_mm=np.rot90(scene.height_mm, 2).copy(),
        albedo=np.rot90(scene.albedo, 2).copy(),
        material_id=np.rot90(scene.material_id, 2).copy(),
        object_mask=np.rot90(scene.object_mask, 2).copy(),
        flat_substrate_mask=np.rot90(scene.flat_substrate_mask, 2).copy(),
        component_mask=np.rot90(scene.component_mask, 2).copy(),
    )


def _reference_scene(config: IdealDatasetConfig) -> SceneMaps:
    shape = (config.height, config.width)
    return SceneMaps(
        height_mm=np.zeros(shape, dtype=np.float32),
        albedo=np.full(shape, 0.72, dtype=np.float32),
        material_id=np.zeros(shape, dtype=np.uint8),
        object_mask=np.zeros(shape, dtype=bool),
        flat_substrate_mask=np.zeros(shape, dtype=bool),
        component_mask=np.zeros(shape, dtype=bool),
    )


def _projector_coordinates(
    config: IdealDatasetConfig, scene: SceneMaps
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    yy, xx = np.indices((config.height, config.width), dtype=np.float32)
    projector_x = (
        xx
        + config.projector_skew_px_per_row * (yy - (config.height - 1) / 2.0)
        + config.height_shift_px_per_mm * scene.height_mm
    )
    stripe_order = np.floor(projector_x / config.projector_period_px).astype(np.int32)
    stripe_order = np.clip(stripe_order, 0, 255)
    phase = np.mod(
        projector_x / config.projector_period_px * (2.0 * np.pi), 2.0 * np.pi
    ).astype(np.float32)
    absolute_phase = (stripe_order * (2.0 * np.pi) + phase).astype(np.float32)
    return stripe_order, phase, absolute_phase


def render_ideal_sequence(
    config: IdealDatasetConfig, scene: SceneMaps
) -> tuple[dict[int, np.ndarray], dict[str, np.ndarray]]:
    stripe_order, phase, absolute_phase = _projector_coordinates(config, scene)
    gray_value = stripe_order ^ (stripe_order >> 1)
    yy, xx = np.indices((config.height, config.width), dtype=np.float32)
    illumination = 0.96 + 0.025 * (xx / max(config.width - 1, 1)) - 0.015 * (
        yy / max(config.height - 1, 1)
    )
    signal = config.signal_level * scene.albedo * illumination
    black = config.black_level + 300.0 * scene.albedo

    projector_patterns: dict[int, np.ndarray] = {
        0: np.ones((config.height, config.width), dtype=np.float32),
        1: np.zeros((config.height, config.width), dtype=np.float32),
    }
    for bit in range(8):
        projector_patterns[2 + bit] = ((gray_value >> (7 - bit)) & 1).astype(
            np.float32
        )
    projector_patterns.update(
        {
            10: 0.5 + config.sine_contrast * np.sin(phase),
            11: 0.5 - config.sine_contrast * np.cos(phase),
            12: 0.5 - config.sine_contrast * np.sin(phase),
            13: 0.5 + config.sine_contrast * np.cos(phase),
        }
    )
    for source_id, inverse_id in zip(range(2, 10), range(14, 22)):
        projector_patterns[inverse_id] = 1.0 - projector_patterns[source_id]

    frames = {
        pattern_id: np.rint(
            np.clip(black + signal * pattern, 0.0, 65535.0)
        ).astype(np.uint16)
        for pattern_id, pattern in projector_patterns.items()
    }
    gt = {
        "height_mm": np.where(scene.object_mask, scene.height_mm, np.nan).astype(
            np.float32
        ),
        "absolute_phase_rad": absolute_phase,
        "stripe_order": stripe_order.astype(np.uint16),
        "material_id": scene.material_id,
        "object_mask": scene.object_mask,
        "flat_substrate_mask": scene.flat_substrate_mask,
        "component_mask": scene.component_mask,
        "visibility_mask": np.ones(scene.object_mask.shape, dtype=bool),
        "shadow_mask": np.zeros(scene.object_mask.shape, dtype=bool),
        "expected_saturation_mask": np.zeros(scene.object_mask.shape, dtype=bool),
    }
    return frames, gt


def _save_mask(path: Path, mask: np.ndarray) -> None:
    Image.fromarray(np.asarray(mask, dtype=np.uint8) * 255).save(path)


def _save_view(
    root: Path,
    view_name: str,
    frames: dict[int, np.ndarray],
    gt: dict[str, np.ndarray],
) -> dict[str, Any]:
    view_dir = root / view_name
    view_dir.mkdir(parents=True, exist_ok=True)
    preview_dir = root / "previews" / view_name
    preview_dir.mkdir(parents=True, exist_ok=True)
    frame_records: dict[str, Any] = {}
    preview_records: dict[str, str] = {}
    for pattern_id, frame in sorted(frames.items()):
        path = view_dir / f"pattern_{pattern_id:03d}.png"
        Image.fromarray(frame).save(path)
        frame_records[str(pattern_id)] = {
            "file": path.name,
            "sha256": sha256_file(path),
            "dtype": str(frame.dtype),
            "shape": list(frame.shape),
        }
        if pattern_id in (0, 2, 10):
            preview_path = preview_dir / f"pattern_{pattern_id:03d}_preview.png"
            Image.fromarray(np.rint(frame.astype(np.float32) / 257.0).astype(np.uint8)).save(
                preview_path
            )
            preview_records[str(pattern_id)] = preview_path.relative_to(root).as_posix()

    gt_dir = root / "gt" / view_name
    gt_dir.mkdir(parents=True, exist_ok=True)
    gt_records: dict[str, Any] = {}
    for name, array in gt.items():
        path = gt_dir / f"{name}.npy"
        np.save(path, array, allow_pickle=False)
        gt_records[name] = {
            "file": path.relative_to(root).as_posix(),
            "sha256": sha256_file(path),
            "dtype": str(array.dtype),
            "shape": list(array.shape),
        }
        if array.dtype == bool:
            _save_mask(gt_dir / f"{name}.png", array)
    finite_height = np.isfinite(gt["height_mm"])
    height_preview = np.zeros(gt["height_mm"].shape, dtype=np.uint8)
    if np.any(finite_height):
        maximum = max(float(np.nanmax(gt["height_mm"])), 1e-6)
        height_preview[finite_height] = np.rint(
            np.clip(gt["height_mm"][finite_height] / maximum, 0.0, 1.0) * 255.0
        ).astype(np.uint8)
    height_preview_path = preview_dir / "height_mm_preview.png"
    Image.fromarray(height_preview).save(height_preview_path)
    material_preview_path = preview_dir / "material_id_preview.png"
    Image.fromarray((gt["material_id"].astype(np.uint16) * 31).astype(np.uint8)).save(
        material_preview_path
    )
    preview_records["height_mm"] = height_preview_path.relative_to(root).as_posix()
    preview_records["material_id"] = material_preview_path.relative_to(root).as_posix()
    return {
        "frames": frame_records,
        "ground_truth": gt_records,
        "previews": preview_records,
    }


def generate_ideal_dataset(
    output_root: str | Path, config: IdealDatasetConfig
) -> Path:
    config.validate()
    output = Path(output_root).expanduser().resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(
            f"output already exists and is not empty: {output}; use a new directory"
        )
    output.mkdir(parents=True, exist_ok=True)

    object_0 = _build_object_scene(config)
    scenes = {
        "object_0": object_0,
        "object_180": _rotate_scene(object_0),
        "reference_0": _reference_scene(config),
        "reference_180": _reference_scene(config),
    }
    view_records: dict[str, Any] = {}
    for view_name in VIEW_NAMES:
        frames, gt = render_ideal_sequence(config, scenes[view_name])
        view_records[view_name] = _save_view(output, view_name, frames, gt)

    # Evaluation aliases use object_0 coordinates. View-specific GT remains in
    # gt/<view>/ and can be aligned independently without entering decode.
    aliases = output / "gt"
    for source_name, alias_name in (
        ("height_mm", "height_mm"),
        ("absolute_phase_rad", "phase"),
        ("material_id", "material_id"),
        ("object_mask", "object_mask"),
    ):
        source = aliases / "object_0" / f"{source_name}.npy"
        target = aliases / f"{alias_name}.npy"
        target.write_bytes(source.read_bytes())

    manifest = {
        "schema_version": 1,
        "validation_level": "L0",
        "validation_kind": "ideal_self_consistency",
        "real_world_accuracy_claim": False,
        "report_notice": "decoder-generator self consistency only",
        "generator": {
            "name": "procedural_structured_light_pcb",
            "seed": config.seed,
            "config": asdict(config),
        },
        "capture_reference_policy": {
            "reference_photo_used_as_geometry_or_calibration": False,
            "qualitative_observations_only": [
                "low_frequency_illumination_nonuniformity",
                "defocus",
                "localized_saturation",
            ],
            "observations_are_excluded_from_ideal_and_available_in_L1_profiles": True,
        },
        "pattern_mapping": {
            "white": 0,
            "black": 1,
            "gray_normal": list(range(2, 10)),
            "sine_4step": [10, 11, 12, 13],
            "gray_inverse": list(range(14, 22)),
        },
        "views": view_records,
        "ground_truth_policy": "evaluation only; never consumed by decode/calibration inference",
    }
    write_json(output / "manifest.json", manifest)
    manifest["output_sha256"] = output_hashes(output)
    write_json(output / "manifest.json", manifest)
    return output
