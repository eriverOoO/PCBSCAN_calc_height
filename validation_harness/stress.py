from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from PIL import Image
from scipy import ndimage

from .manifests import (
    assert_seed_partition,
    load_config,
    output_hashes,
    pattern_files,
    sha256_file,
    write_json,
)
from .source_domain import source_domain_from_profile


VIEW_NAMES = ("object_0", "object_180", "reference_0", "reference_180")
VIEW_SEED_OFFSETS = {name: index * 10_000 for index, name in enumerate(VIEW_NAMES)}


@dataclass(frozen=True)
class StressResult:
    images: dict[int, np.ndarray]
    masks: dict[str, np.ndarray]
    manifest: dict[str, Any]


def _range_pair(value: Any, default: tuple[float, float]) -> tuple[float, float]:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        limit = abs(float(value))
        return -limit, limit
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"expected [minimum, maximum], got {value!r}")
    return float(value[0]), float(value[1])


def _odd_kernel(value: int) -> int:
    size = max(0, int(value))
    return size + 1 if size > 0 and size % 2 == 0 else size


def _warp(image: np.ndarray, transform: Mapping[str, float], order: int) -> np.ndarray:
    angle = float(transform.get("rotation_deg", 0.0))
    shift_y = float(transform.get("translation_y_px", 0.0))
    shift_x = float(transform.get("translation_x_px", 0.0))
    result = np.asarray(image)
    if angle:
        result = ndimage.rotate(
            result,
            angle=angle,
            reshape=False,
            order=order,
            mode="reflect" if order else "nearest",
            prefilter=order > 1,
        )
    if shift_x or shift_y:
        result = ndimage.shift(
            result,
            shift=(shift_y, shift_x),
            order=order,
            mode="reflect" if order else "nearest",
            prefilter=order > 1,
        )
    return result


class StressSynthesizer:
    """Deterministic image-domain equipment non-ideality synthesizer.

    Effects are applied to linear-radiance arrays where practical.  Geometric
    warps and the intentionally injected Gray/cycle-slip errors are explicitly
    recorded as image-domain approximations in the manifest.
    """

    def __init__(self, profile: Mapping[str, Any], seed: int):
        self.profile = dict(profile)
        self.seed = int(seed)
        self._sensor_shape: tuple[int, int] | None = None
        self._fpn: np.ndarray | None = None
        self._hot_mask: np.ndarray | None = None
        self._dead_mask: np.ndarray | None = None

    @classmethod
    def from_file(cls, path: str | Path, seed: int) -> "StressSynthesizer":
        return cls(load_config(path), seed)

    def _ensure_sensor(self, shape: tuple[int, int]) -> None:
        if self._sensor_shape is not None:
            if self._sensor_shape != shape:
                raise ValueError("all views in one case must use the same sensor shape")
            return
        rng = np.random.default_rng(self.seed + 7919)
        noise = self.profile.get("noise", {})
        defects = self.profile.get("defects", {})
        fpn_sigma = float(noise.get("fixed_pattern_sigma", 0.0))
        self._fpn = rng.normal(0.0, fpn_sigma, shape).astype(np.float32)
        self._hot_mask = rng.random(shape) < float(defects.get("hot_pixel_fraction", 0.0))
        self._dead_mask = rng.random(shape) < float(defects.get("dead_pixel_fraction", 0.0))
        clusters = max(0, int(defects.get("cluster_count", 0)))
        radius = max(1, int(defects.get("cluster_radius_px", 1)))
        yy, xx = np.indices(shape)
        for index in range(clusters):
            cy = int(rng.integers(0, shape[0]))
            cx = int(rng.integers(0, shape[1]))
            cluster = (yy - cy) ** 2 + (xx - cx) ** 2 <= radius**2
            (self._hot_mask if index % 2 == 0 else self._dead_mask)[cluster] = True
        self._sensor_shape = shape

    def synthesize(
        self,
        images: Mapping[int, np.ndarray],
        *,
        view_name: str,
    ) -> StressResult:
        if view_name not in VIEW_SEED_OFFSETS:
            raise ValueError(f"unknown validation view: {view_name}")
        if sorted(images) != list(range(22)):
            raise ValueError("stress synthesis requires exact pattern ids 0..21")
        shape = tuple(np.asarray(images[0]).shape)
        if len(shape) != 2 or any(tuple(np.asarray(image).shape) != shape for image in images.values()):
            raise ValueError("all stress input frames must be same-shape monochrome images")
        self._ensure_sensor(shape)  # shared across every frame/view in the virtual sensor
        assert self._fpn is not None and self._hot_mask is not None and self._dead_mask is not None

        rng = np.random.default_rng(self.seed + VIEW_SEED_OFFSETS[view_name])
        height, width = shape
        yy, xx = np.indices(shape, dtype=np.float32)
        xn = (xx - (width - 1) / 2.0) / max(width / 2.0, 1.0)
        yn = (yy - (height - 1) / 2.0) / max(height / 2.0, 1.0)
        radiometric = self.profile.get("radiometric", {})
        optics = self.profile.get("optics", {})
        noise = self.profile.get("noise", {})
        defects = self.profile.get("defects", {})
        registration = self.profile.get("registration", {})
        gray_stress = self.profile.get("gray_stress", {})
        surface = self.profile.get("surface", {})
        source_gain, source_domain_manifest = source_domain_from_profile(self.profile, shape)

        gain_limit = abs(float(radiometric.get("pattern_gain_max_fraction", 0.0)))
        frame_gains = {
            pattern_id: float(rng.uniform(1.0 - gain_limit, 1.0 + gain_limit))
            for pattern_id in range(22)
        }
        gamma = float(radiometric.get("gamma", 1.0))
        harmonic2 = float(radiometric.get("sine_harmonic_2", 0.0))
        harmonic3 = float(radiometric.get("sine_harmonic_3", 0.0))
        vignette = float(radiometric.get("vignette", 0.0))
        illumination = 1.0 - vignette * np.clip(xn * xn + yn * yn, 0.0, 1.0)
        gradient = float(radiometric.get("low_frequency_gradient", 0.0))
        illumination *= 1.0 + gradient * (0.65 * xn + 0.35 * yn)

        shadow_fraction = float(surface.get("shadow_fraction", 0.0))
        shadow_mask = xn < (-1.0 + 2.0 * shadow_fraction) if shadow_fraction else np.zeros(shape, bool)
        shadow_expand = max(0, int(surface.get("shadow_expand_px", 0)))
        if shadow_expand:
            shadow_mask = ndimage.binary_dilation(shadow_mask, iterations=shadow_expand)
        shadow_transmission = float(surface.get("shadow_transmission", 1.0))
        low_reflect_mask = (xn > 0.15) & (xn < 0.65) & (yn > -0.55) & (yn < 0.15)
        low_reflect_scale = float(surface.get("low_reflectance_scale", 1.0))
        metal_mask = (xn > -0.65) & (xn < -0.1) & (yn > -0.35) & (yn < 0.35)
        metal_gain = max(0.0, float(surface.get("metal_gain", 1.0)))

        source_gray = [np.asarray(images[index], dtype=np.float32) for index in range(2, 10)]
        gray_boundary = np.zeros(shape, dtype=bool)
        for frame in source_gray:
            scale = 65535.0 if float(np.nanmax(frame)) > 255.0 else 255.0
            normalized = frame / scale
            gradient_mag = np.hypot(ndimage.sobel(normalized, 0), ndimage.sobel(normalized, 1))
            gray_boundary |= gradient_mag > float(gray_stress.get("boundary_gradient", 0.25))
        boundary_radius = max(0, int(gray_stress.get("boundary_radius_px", 0)))
        if boundary_radius:
            gray_boundary = ndimage.binary_dilation(gray_boundary, iterations=boundary_radius)
        bit_flip_fraction = float(gray_stress.get("bit_flip_fraction", 0.0))
        bit_flip_mask = gray_boundary & (rng.random(shape) < bit_flip_fraction)

        cycle_fraction = float(gray_stress.get("cycle_slip_fraction", 0.0))
        cycle_slip_mask = np.zeros(shape, dtype=bool)
        if cycle_fraction > 0:
            band_width = max(1, int(round(width * cycle_fraction)))
            start = int(rng.integers(0, max(1, width - band_width + 1)))
            cycle_slip_mask[:, start : start + band_width] = True
        half_cycle = cycle_slip_mask & (yy < height / 2.0)
        whole_cycle = cycle_slip_mask & ~half_cycle

        translation_min, translation_max = _range_pair(
            registration.get("translation_px"), (0.0, 0.0)
        )
        rotation_min, rotation_max = _range_pair(
            registration.get("rotation_deg"), (0.0, 0.0)
        )
        transform = {
            "translation_x_px": float(rng.uniform(translation_min, translation_max)),
            "translation_y_px": float(rng.uniform(translation_min, translation_max)),
            "rotation_deg": float(rng.uniform(rotation_min, rotation_max)),
            "coordinate_system": "output pixel coordinates; +x right, +y down, rotation scipy CCW",
            "gt_comparison": "warp prediction/masks into the declared object_0 coordinates before metrics",
        }
        if view_name == "object_180":
            center_error = abs(float(registration.get("rotation_180_center_error_px", 0.0)))
            fine_rotation = abs(float(registration.get("rotation_180_extra_deg", 0.0)))
            transform["translation_x_px"] += float(rng.uniform(-center_error, center_error))
            transform["translation_y_px"] += float(rng.uniform(-center_error, center_error))
            transform["rotation_deg"] += float(rng.uniform(-fine_rotation, fine_rotation))

        projector_sigma = max(0.0, float(optics.get("projector_psf_sigma_px", 0.0)))
        camera_sigma = max(0.0, float(optics.get("camera_psf_sigma_px", 0.0)))
        defocus_sigma = max(0.0, float(optics.get("spatial_defocus_sigma_px", 0.0)))
        flare = max(0.0, float(radiometric.get("flare_fraction", 0.0)))
        multipath = max(0.0, float(surface.get("multipath_halo_fraction", 0.0)))
        bloom_sigma = max(0.0, float(surface.get("bloom_sigma_px", 0.0)))
        bloom_gain = max(0.0, float(surface.get("bloom_gain", 0.0)))
        clipping = float(radiometric.get("clipping_level", 1.0))

        output: dict[int, np.ndarray] = {}
        saturation_mask = np.zeros(shape, dtype=bool)
        for pattern_id in range(22):
            raw = np.asarray(images[pattern_id])
            maximum = 65535.0 if raw.dtype == np.uint16 or float(np.nanmax(raw)) > 255.0 else 255.0
            linear = np.clip(raw.astype(np.float32) / maximum, 0.0, 1.0)
            if projector_sigma:
                linear = ndimage.gaussian_filter(linear, projector_sigma, mode="reflect")
            if defocus_sigma:
                blurred = ndimage.gaussian_filter(
                    linear, projector_sigma + defocus_sigma, mode="reflect"
                )
                blend = np.clip((xn + 1.0) / 2.0, 0.0, 1.0)
                linear = linear * (1.0 - blend) + blurred * blend
            linear *= illumination * frame_gains[pattern_id]
            if source_gain is not None:
                # Physical-background proxy only; this is deliberately not
                # interpreted as a fitted PSF/gamma/noise/distortion value.
                linear *= source_gain
            linear[shadow_mask] *= shadow_transmission
            linear[low_reflect_mask] *= low_reflect_scale
            linear[metal_mask] *= metal_gain
            if pattern_id in range(10, 14):
                centered = 2.0 * linear - 1.0
                linear += harmonic2 * (2.0 * centered**2 - 1.0)
                linear += harmonic3 * (4.0 * centered**3 - 3.0 * centered)
                shifted = np.roll(linear, max(1, width // 32), axis=1)
                linear[half_cycle] = shifted[half_cycle]
                shifted_whole = np.roll(linear, max(1, width // 16), axis=1)
                linear[whole_cycle] = shifted_whole[whole_cycle]
            linear = np.clip(linear, 0.0, None) ** gamma
            if pattern_id in range(2, 10) or pattern_id in range(14, 22):
                linear[bit_flip_mask] = 1.0 - linear[bit_flip_mask]
                linear[whole_cycle] = 1.0 - linear[whole_cycle]
            if flare:
                linear += flare * float(np.mean(linear))
            if multipath:
                halo = ndimage.gaussian_filter(linear * metal_mask, max(1.0, bloom_sigma or 2.0))
                linear += multipath * halo
            if bloom_gain and bloom_sigma:
                bright = np.clip(linear - 0.85, 0.0, None)
                linear += bloom_gain * ndimage.gaussian_filter(bright, bloom_sigma)
            if camera_sigma:
                linear = ndimage.gaussian_filter(linear, camera_sigma, mode="reflect")
            linear = np.clip(linear, 0.0, clipping)
            frame_saturation = linear >= min(clipping, 1.0)

            # Re-mount error belongs to the object/reference radiance sequence.
            # Sensor FPN/hot/dead pixels and sensor noise are applied afterwards,
            # so they remain fixed in camera coordinates across every view.
            linear = _warp(linear, transform, order=1)
            saturation_mask |= _warp(frame_saturation.astype(np.uint8), transform, order=0) > 0

            electrons = max(1.0, float(noise.get("poisson_electrons", 0.0)))
            if float(noise.get("poisson_electrons", 0.0)) > 0:
                linear = rng.poisson(np.clip(linear, 0, 1) * electrons) / electrons
            linear += rng.normal(0.0, float(noise.get("read_sigma", 0.0)), shape)
            linear += rng.normal(0.0, float(noise.get("row_sigma", 0.0)), (height, 1))
            linear += rng.normal(0.0, float(noise.get("column_sigma", 0.0)), (1, width))
            linear += self._fpn
            linear[self._hot_mask] = 1.0
            linear[self._dead_mask] = 0.0

            quantization_bits = int(noise.get("quantization_bits", 16))
            if quantization_bits < 1 or quantization_bits > 16:
                raise ValueError("noise.quantization_bits must be between 1 and 16")
            if quantization_bits < 16:
                adc_max = float((1 << quantization_bits) - 1)
                linear = np.rint(np.clip(linear, 0.0, 1.0) * adc_max) / adc_max
            output[pattern_id] = np.rint(np.clip(linear, 0.0, 1.0) * 65535.0).astype(
                np.uint16
            )

        scene_masks = {
            "bit_flip": bit_flip_mask,
            "cycle_slip": cycle_slip_mask,
            "half_cycle_slip": half_cycle,
            "whole_cycle_slip": whole_cycle,
            "saturation": saturation_mask,
            "shadow": shadow_mask,
            "gray_boundary": gray_boundary,
            "registration_error": np.ones(shape, dtype=bool)
            if any(abs(float(transform[key])) > 1e-12 for key in (
                "translation_x_px", "translation_y_px", "rotation_deg"
            ))
            else np.zeros(shape, dtype=bool),
        }
        masks = {
            name: _warp(mask.astype(np.uint8), transform, order=0) > 0
            for name, mask in scene_masks.items()
        }
        masks["hot_pixel"] = self._hot_mask | self._dead_mask
        manifest = {
            "view": view_name,
            "seed": self.seed + VIEW_SEED_OFFSETS[view_name],
            "frame_gains": {str(key): value for key, value in frame_gains.items()},
            "object_reference_transform": transform,
            "impairments": {
                "radiometric": radiometric,
                "optics": optics,
                "noise": noise,
                "defects": defects,
                "registration": registration,
                "surface": surface,
                "gray_stress": gray_stress,
            },
            "source_domain": source_domain_manifest,
            "approximation": {
                "radiometric_and_noise": "linear_radiance_domain",
                "registration_gray_and_cycle_slip": "image_domain",
            },
            "mask_names": sorted(masks),
        }
        return StressResult(output, masks, manifest)


def load_ideal_views(root: str | Path) -> dict[str, dict[int, np.ndarray]]:
    folder = Path(root).expanduser().resolve()
    views: dict[str, dict[int, np.ndarray]] = {}
    aliases = {
        "object_0": ("object_0", "deg_0", "angle_000"),
        "object_180": ("object_180", "deg_180", "angle_180"),
        "reference_0": ("reference_0", "reference_deg_0"),
        "reference_180": ("reference_180", "reference_deg_180"),
    }
    root_mapping = pattern_files(folder)
    for view, names in aliases.items():
        source = next((folder / name for name in names if (folder / name).is_dir()), folder)
        mapping = pattern_files(source)
        if len(mapping) != 22:
            if len(root_mapping) == 22:
                mapping = root_mapping
            else:
                raise FileNotFoundError(
                    f"{view} needs pattern_000..pattern_021 below {folder}"
                )
        loaded: dict[int, np.ndarray] = {}
        for pattern_id, path in mapping.items():
            with Image.open(path) as image:
                loaded[pattern_id] = np.asarray(image).copy()
        views[view] = loaded
    return views


def generate_stress_case(
    *,
    input_root: str | Path,
    output_root: str | Path,
    profile_path: str | Path,
    seed: int,
    partition: str,
) -> Path:
    assert_seed_partition(seed, partition)
    source_root = Path(input_root).expanduser().resolve()
    destination = Path(output_root).expanduser().resolve() / f"case_{seed}"
    if destination.exists():
        raise FileExistsError(
            f"output already exists: {destination}; choose a new output root to preserve prior results"
        )
    profile = load_config(profile_path)
    source_domain = profile.get("source_domain")
    if isinstance(source_domain, dict):
        # Configs are checked into the repository and are commonly launched
        # from another working directory (e.g. a double-clicked BAT file).
        # Resolve repository-relative evidence paths once, before synthesis.
        workspace = Path(__file__).resolve().parents[1]
        for key in ("background_path", "gain_map_path"):
            raw = source_domain.get(key)
            if raw and not Path(raw).expanduser().is_absolute():
                candidate = (workspace / str(raw)).resolve()
                if not candidate.exists():
                    candidate = (Path.cwd() / str(raw)).resolve()
                source_domain[key] = str(candidate)
    synthesizer = StressSynthesizer(profile, seed)
    views = load_ideal_views(source_root)
    view_manifests: dict[str, Any] = {}
    for view_name in VIEW_NAMES:
        result = synthesizer.synthesize(views[view_name], view_name=view_name)
        view_dir = destination / "views" / view_name
        view_dir.mkdir(parents=True, exist_ok=True)
        for pattern_id, image in result.images.items():
            Image.fromarray(image).save(view_dir / f"pattern_{pattern_id:03d}.png")
        mask_dir = destination / "masks" / view_name
        mask_dir.mkdir(parents=True, exist_ok=True)
        for mask_name, mask in result.masks.items():
            Image.fromarray((mask.astype(np.uint8) * 255)).save(mask_dir / f"{mask_name}.png")
        view_manifests[view_name] = result.manifest

    gt_source = source_root / "gt"
    if gt_source.is_dir():
        shutil.copytree(gt_source, destination / "gt")
    source_hashes = {
        path.relative_to(source_root).as_posix(): sha256_file(path)
        for path in sorted(source_root.rglob("pattern_*.*"))
        if path.is_file()
    }
    manifest = {
        "schema_version": 1,
        "validation_level": "L1",
        "validation_kind": "deterministic_stress_synthesis",
        "real_world_accuracy_claim": False,
        "stress_envelope": profile.get(
            "stress_envelope", "uncalibrated stress envelope"
        ),
        "seed": int(seed),
        "seed_partition": partition,
        "profile": profile,
        "source_pattern_sha256": source_hashes,
        "views": view_manifests,
    }
    write_json(destination / "manifest.json", manifest)
    manifest["output_sha256"] = output_hashes(destination)
    write_json(destination / "manifest.json", manifest)
    return destination
