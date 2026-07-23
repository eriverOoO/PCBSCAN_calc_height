from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .manifests import output_hashes, sha256_file, write_json


VIEW_NAMES = ("object_0", "object_180", "reference_0", "reference_180")
BOARD_PROFILES = (
    "procedural_generic",
    "adafruit_bme280",
    "soldered_simple_light",
    "soldered_w5500",
)

BOARD_PROFILE_METADATA: dict[str, dict[str, Any]] = {
    "procedural_generic": {
        "display_name": "Generic procedural PCB",
        "geometry_basis": "project-local synthetic fixture",
        "physical_size_mm": None,
        "source_url": None,
        "license": "project license",
    },
    "adafruit_bme280": {
        "display_name": "Adafruit BME280 breakout (product 2652)",
        "geometry_basis": "independent raster approximation informed by upstream STL bounds",
        "physical_size_mm": [17.78, 19.05],
        "source_url": "https://github.com/adafruit/Adafruit_CAD_Parts/tree/main/2652%20Adafruit%20BME280",
        "license": "MIT",
    },
    "soldered_simple_light": {
        "display_name": "Soldered Simple light sensor board V1.1.1",
        "geometry_basis": "independent raster approximation informed by KiCad Edge.Cuts, BOM and product view",
        "physical_size_mm": [22.0, 22.0],
        "source_url": "https://github.com/SolderedElectronics/Simple-light-sensor-board-hardware-design",
        "license": "TAPR Open Hardware License 1.0 (upstream hardware documentation)",
    },
    "soldered_w5500": {
        "display_name": "Soldered Ethernet controller W5500 board V1.2.0",
        "geometry_basis": "independent raster approximation informed by KiCad Edge.Cuts, BOM and product view",
        "physical_size_mm": [38.0, 54.0],
        "source_url": "https://github.com/SolderedElectronics/Ethernet-controller-W5500-board-hardware-design",
        "license": "TAPR Open Hardware License 1.0 (upstream hardware documentation)",
    },
}


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
    board_profile: str = "procedural_generic"
    reference_board_max_height_mm: float = 1.9
    projector_radial_k1: float = 0.0
    projector_optical_axis_offset_px: tuple[float, float] = (0.0, 0.0)

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
        if self.board_profile not in BOARD_PROFILES:
            raise ValueError(
                f"unknown board_profile {self.board_profile!r}; choose one of {BOARD_PROFILES}"
            )
        if not 0.0 < self.reference_board_max_height_mm < 2.0:
            raise ValueError("reference_board_max_height_mm must be in (0, 2.0)")
        if len(self.projector_optical_axis_offset_px) != 2:
            raise ValueError("projector_optical_axis_offset_px must contain x and y")


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


def _build_generic_scene(config: IdealDatasetConfig) -> SceneMaps:
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

    # Keep every generated fixture inside the project-wide physical envelope.
    # The generic scene uses deliberately exaggerated component archetypes so
    # clipping here is explicit and recorded rather than silently violating
    # the requested <2 mm maximum height.
    np.minimum(height_mm, config.reference_board_max_height_mm, out=height_mm)
    components = board & (height_mm > 0)
    return SceneMaps(
        height_mm=height_mm,
        albedo=albedo,
        material_id=material_id,
        object_mask=board,
        flat_substrate_mask=board & ~components,
        component_mask=components,
    )


def _build_reference_board_scene(config: IdealDatasetConfig) -> SceneMaps:
    """Rasterize source-informed board signatures without redistributing CAD geometry."""
    height, width = config.height, config.width
    rng = np.random.default_rng(config.seed)
    yy, xx = np.indices((height, width), dtype=np.float32)
    cx = (width - 1) / 2.0
    cy = (height - 1) / 2.0
    profile = config.board_profile
    physical_width, physical_height = BOARD_PROFILE_METADATA[profile]["physical_size_mm"]
    scale = min(width * 0.68 / physical_width, height * 0.72 / physical_height)

    def px_x(mm: float) -> float:
        return cx + mm * scale

    def px_y(mm: float) -> float:
        return cy + mm * scale

    board = _rounded_rect(
        xx,
        yy,
        center_x=cx,
        center_y=cy,
        half_width=physical_width * scale / 2.0,
        half_height=physical_height * scale / 2.0,
        radius=max(scale * 1.0, 2.0),
    )
    height_mm = np.zeros((height, width), dtype=np.float32)
    material_id = np.zeros((height, width), dtype=np.uint8)
    albedo = np.full((height, width), 0.72, dtype=np.float32)
    material_id[board] = 1
    base_albedo = {
        "adafruit_bme280": 0.44,
        "soldered_simple_light": 0.34,
        "soldered_w5500": 0.34,
    }[profile]
    texture = 0.010 * np.sin(xx / 17.0 + rng.uniform(0, 2 * np.pi)) * np.cos(
        yy / 21.0 + rng.uniform(0, 2 * np.pi)
    )
    albedo[board] = base_albedo + texture[board]

    def rect(
        x_mm: float,
        y_mm: float,
        width_mm: float,
        height_mm_value: float,
        z_mm: float,
        material: int,
        reflectance: float,
    ) -> None:
        mask = _rect(
            xx,
            yy,
            px_x(x_mm),
            px_y(y_mm),
            width_mm * scale / 2.0,
            height_mm_value * scale / 2.0,
        ) & board
        height_mm[mask] = np.maximum(height_mm[mask], z_mm)
        material_id[mask] = material
        albedo[mask] = reflectance

    def circle(
        x_mm: float,
        y_mm: float,
        radius_mm: float,
        z_mm: float,
        material: int,
        reflectance: float,
    ) -> np.ndarray:
        mask = (
            (xx - px_x(x_mm)) ** 2 + (yy - px_y(y_mm)) ** 2
            <= (radius_mm * scale) ** 2
        ) & board
        height_mm[mask] = np.maximum(height_mm[mask], z_mm)
        material_id[mask] = material
        albedo[mask] = reflectance
        return mask

    def hole(x_mm: float, y_mm: float, radius_mm: float) -> None:
        mask = (
            (xx - px_x(x_mm)) ** 2 + (yy - px_y(y_mm)) ** 2
            <= (radius_mm * scale) ** 2
        )
        board[mask] = False
        height_mm[mask] = 0.0
        material_id[mask] = 0
        albedo[mask] = 0.72

    if profile == "adafruit_bme280":
        for x_pos in (-5.8, 5.8):
            circle(x_pos, -6.1, 2.1, 0.12, 2, 0.90)
            hole(x_pos, -6.1, 1.15)
        for x_pos in np.linspace(-6.3, 6.3, 7):
            circle(float(x_pos), 7.2, 0.82, 0.18, 2, 0.90)
            hole(float(x_pos), 7.2, 0.42)
        rect(1.2, -0.8, 3.0, 3.0, 1.15, 4, 0.18)  # BME280 LGA
        rect(-4.1, -1.7, 3.3, 1.8, 1.35, 4, 0.13)
        rect(-1.2, 3.0, 3.0, 1.6, 1.25, 4, 0.13)
        rect(4.0, 2.5, 2.5, 1.5, 1.20, 4, 0.13)
        for item in ((-4.0, 1.2), (-2.2, 0.6), (1.0, 2.8), (3.6, 0.0), (0.0, -4.0)):
            rect(*item, 1.8, 1.1, 0.85, 6, 0.72)
    elif profile == "soldered_simple_light":
        for x_pos in (-8.0, 8.0):
            circle(x_pos, 8.0, 2.2, 0.12, 2, 0.90)
            hole(x_pos, 8.0, 1.6)
        for x_pos in (-7.6, -2.5, 2.5, 7.6):
            circle(x_pos, -9.5, 0.8, 0.18, 2, 0.88)
            hole(x_pos, -9.5, 0.42)
        rect(0.0, 0.0, 5.2, 5.0, 1.75, 4, 0.13)  # LM393 SOIC-8
        rect(-6.0, 0.0, 4.5, 4.5, 2.15, 7, 0.30)  # trimmer
        circle(8.8, 0.2, 2.2, 4.8, 6, 0.60)  # raised LDR body
        for item in ((2.0, -3.5), (4.2, 3.4), (8.0, 0.0), (8.0, 2.0), (6.5, -4.0)):
            rect(*item, 1.7, 1.0, 0.80, 6, 0.72)
        rect(0.0, 4.3, 5.2, 2.2, 2.8, 7, 0.28)
    elif profile == "soldered_w5500":
        for x_pos in (-16.0, 16.0):
            for y_pos in (-24.0, 24.0):
                circle(x_pos, y_pos, 2.2, 0.12, 2, 0.90)
                hole(x_pos, y_pos, 1.6)
        rect(0.0, -16.0, 17.0, 16.0, 13.5, 7, 0.32)  # RJ-45
        rect(0.0, 8.0, 7.0, 7.0, 1.20, 4, 0.13)  # W5500 QFN
        rect(12.0, 16.0, 4.4, 5.2, 1.15, 4, 0.13)  # level shifter
        rect(-15.8, 8.0, 2.2, 20.0, 2.8, 7, 0.28)  # 9-pin header
        for y_pos in np.linspace(18.0, 25.5, 9):
            circle(0.0, float(y_pos), 0.72, 0.18, 2, 0.90)
        for item in (
            (-7.2, 4.2), (-7.2, 6.6), (-7.2, 8.0), (-7.2, 9.6),
            (5.8, 0.0), (5.8, 2.0), (5.8, 4.0), (8.5, 4.0),
            (10.0, 8.0), (12.0, 10.0), (-1.5, 16.5), (3.0, 17.0),
        ):
            rect(*item, 1.7, 1.0, 0.80, 6, 0.72)
        circle(-8.1, 16.0, 2.1, 3.8, 6, 0.64)
        circle(10.0, 0.5, 2.1, 3.8, 6, 0.64)

    np.minimum(height_mm, config.reference_board_max_height_mm, out=height_mm)
    components = board & (height_mm > 0)
    return SceneMaps(
        height_mm=height_mm,
        albedo=albedo,
        material_id=material_id,
        object_mask=board,
        flat_substrate_mask=board & ~components,
        component_mask=components,
    )


def _build_object_scene(config: IdealDatasetConfig) -> SceneMaps:
    if config.board_profile == "procedural_generic":
        return _build_generic_scene(config)
    return _build_reference_board_scene(config)


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
    optical_x = (config.width - 1) / 2.0 + config.projector_optical_axis_offset_px[0]
    optical_y = (config.height - 1) / 2.0 + config.projector_optical_axis_offset_px[1]
    nx = (xx - optical_x) / max(config.width - 1, 1)
    ny = (yy - optical_y) / max(config.height - 1, 1)
    radial_scale = 1.0 + config.projector_radial_k1 * (nx * nx + ny * ny)
    distorted_x = optical_x + (xx - optical_x) * radial_scale
    projector_x = (
        distorted_x
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
        "board_model": BOARD_PROFILE_METADATA[config.board_profile],
        "height_policy": {
            "reference_board_max_height_mm": config.reference_board_max_height_mm,
            "meaning": "relative height above the simulated PCB top surface",
            "source_cad_z_used_directly": False,
        },
        "scanner_model": {
            "design_basis": "camera/projector separation and calibrated light-transport controls adapted from scanner-sim concepts",
            "upstream_reference": "https://geometryprocessing.github.io/scanner-sim/",
            "camera": {
                "model": "pinhole raster sensor",
                "pixel_coordinates": "OpenCV convention; origin at center of top-left pixel",
            },
            "projector": {
                "model": "independent pinhole coded-light source",
                "optical_axis_offset_px": list(config.projector_optical_axis_offset_px),
                "radial_k1": config.projector_radial_k1,
            },
            "focus_and_radiometric_nonidealities": "kept in L1 profiles, outside ideal self-consistency",
            "ground_truth_is_decoder_input": False,
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
