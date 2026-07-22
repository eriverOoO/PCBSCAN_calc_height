from __future__ import annotations

import abc
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .manifests import sha256_file, write_json


def blender_setup_message() -> str:
    return (
        "Blender/Cycles is not available. Install Blender 4.x, then pass "
        "--blender <path-to-blender.exe> or set BLENDER_EXECUTABLE."
    )


def _source_patterns(root: Path) -> dict[int, Path]:
    mapping: dict[int, Path] = {}
    for pattern_id in range(14):
        matches: list[Path] = []
        for expression in (
            f"pattern_{pattern_id:03d}.*",
            f"{pattern_id:02d}.*",
            f"{pattern_id:03d}.*",
        ):
            matches.extend(root.glob(expression))
        matches = sorted({path for path in matches if path.suffix.lower() in {".bmp", ".png", ".tif", ".tiff"}})
        if matches:
            mapping[pattern_id] = matches[0]
    missing = [pattern_id for pattern_id in range(14) if pattern_id not in mapping]
    if missing:
        raise FileNotFoundError(f"exact source patterns 0..13 are required; missing {missing}")
    return mapping


def prepare_exact_22_patterns(input_root: str | Path, output_root: str | Path) -> dict[str, Any]:
    """Copy actual 14 patterns and generate only the eight Gray complements."""
    source_root = Path(input_root).expanduser().resolve()
    output = Path(output_root).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = _source_patterns(source_root)
    mapping: dict[str, Any] = {}
    arrays: dict[int, np.ndarray] = {}
    for pattern_id, source_path in sorted(source.items()):
        with Image.open(source_path) as image:
            array = np.asarray(image)
        if array.ndim == 3:
            array = np.asarray(Image.open(source_path).convert("L"))
        arrays[pattern_id] = array.copy()
        output_path = output / f"pattern_{pattern_id:03d}.png"
        Image.fromarray(array).save(output_path)
        mapping[str(pattern_id)] = {
            "label": source_path.stem,
            "origin": "actual_pattern",
            "source": str(source_path),
            "sha256": sha256_file(output_path),
        }
    for source_id, target_id in zip(range(2, 10), range(14, 22)):
        array = arrays[source_id]
        maximum = np.iinfo(array.dtype).max if np.issubdtype(array.dtype, np.integer) else 1.0
        inverse = (maximum - array).astype(array.dtype)
        output_path = output / f"pattern_{target_id:03d}.png"
        Image.fromarray(inverse).save(output_path)
        mapping[str(target_id)] = {
            "label": f"gray{source_id - 2}_inv",
            "origin": "exact_gray_inverse",
            "inverse_of": source_id,
            "sha256": sha256_file(output_path),
        }
    return {
        "pattern_count": 22,
        "pattern_order": list(range(22)),
        "mapping": mapping,
        "output_root": str(output),
    }


def build_scene_manifest(
    *, pattern_manifest: dict[str, Any], seed: int, backend: str = "blender_cycles"
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "validation_level": "L2",
        "validation_kind": "physically_based_rendering",
        "real_world_accuracy_claim": False,
        "backend": backend,
        "backend_status": "scaffold_requires_projector_gobo_and_gt_pass_validation",
        "seed": int(seed),
        "patterns": pattern_manifest,
        "simulation_design": {
            "reference": "https://geometryprocessing.github.io/scanner-sim/",
            "adapted_concepts": [
                "independent calibrated camera and projector",
                "custom coded-light pattern sequence",
                "separate camera and projector focus models",
                "object-only turntable rotation",
                "rendered frames paired with depth and geometry ground truth",
            ],
            "implementation_note": "project-local Blender/Cycles boundary; no scanner-sim GPL rendering code is copied",
        },
        "camera": {
            "model": "pinhole",
            "reference_sensor": "XIMEA IMX174",
            "resolution_px": [1936, 1216],
            "pixel_pitch_um": 5.86,
            "focal_length_mm": 35.0,
            "automatic_exposure": False,
            "frame_normalization": False,
            "focus_model": "thin_lens_pending_calibration",
            "pixel_coordinates": "OpenCV convention; origin at center of top-left pixel",
        },
        "projector": {
            "model": "independent_pinhole_gobo",
            "texture_sequence": "exact_22_patterns",
            "camera_fixed_for_all_views": True,
            "focus_model": "independent_projector_lens_pending_calibration",
            "optical_axis": "explicit calibration parameter",
        },
        "views": {
            "object_0": {"pcb_rotation_deg": 0.0, "pcb_present": True},
            "object_180": {"pcb_rotation_deg": 180.0, "pcb_present": True},
            "reference_0": {"pcb_rotation_deg": 0.0, "pcb_present": False},
            "reference_180": {"pcb_rotation_deg": 180.0, "pcb_present": False},
        },
        "reference": "independent empty matte stage render; PCB removed",
        "materials": [
            "pcb_substrate",
            "solder_mask",
            "copper_gold_tin_pad",
            "solder",
            "matte_black_ic",
            "ceramic_smd",
            "connector",
        ],
        "geometry": {
            "initial": "procedural mesh with separate substrate, pads, IC, SMD, solder and connector meshes",
            "importers": ["glb", "gltf"],
            "step_conversion": "convert STEP with FreeCAD/KiCad StepUp or export KiCad GLB before Blender import",
        },
        "integrator": {
            "engine": "CYCLES",
            "effects": ["shadow", "interreflection", "specular_highlight", "occlusion"],
        },
        "output": {
            "decoder_frames": "mono 16-bit PNG",
            "ground_truth": [
                "metric_depth",
                "height",
                "normals",
                "material_id",
                "object_mask",
                "visibility",
                "shadow",
                "expected_saturation",
                "camera_projector_calibration",
            ],
        },
    }


class RendererBackend(abc.ABC):
    name: str

    @abc.abstractmethod
    def available(self) -> bool:
        raise NotImplementedError

    @abc.abstractmethod
    def render(self, manifest_path: Path, output_root: Path) -> None:
        raise NotImplementedError


class BlenderCyclesBackend(RendererBackend):
    name = "blender_cycles"

    def __init__(self, executable: str | Path | None = None):
        configured = executable or os.environ.get("BLENDER_EXECUTABLE") or shutil.which("blender")
        self.executable = Path(configured).expanduser().resolve() if configured else None

    def available(self) -> bool:
        return self.executable is not None and self.executable.is_file()

    def render(self, manifest_path: Path, output_root: Path) -> None:
        if not self.available():
            raise RuntimeError(blender_setup_message())
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("backend_status") != "validated":
            raise RuntimeError(
                "Blender scene scaffold is present, but exact projector-gobo and GT-pass "
                "output have not been validated on Blender. Use --manifest-only; do not "
                "treat experimental frames as decoder validation input."
            )
        script = Path(__file__).resolve().parents[1] / "tools" / "blender_render_scene.py"
        command = [
            str(self.executable),
            "--background",
            "--python",
            str(script),
            "--",
            "--scene-manifest",
            str(manifest_path.resolve()),
            "--output-root",
            str(output_root.resolve()),
        ]
        subprocess.run(command, check=True)


class PbrtBackendAdapter(RendererBackend):
    """Stable adapter boundary for a future PBRT implementation."""

    name = "pbrt"

    def available(self) -> bool:
        return False

    def render(self, manifest_path: Path, output_root: Path) -> None:
        raise RuntimeError("PBRT adapter is defined but no PBRT executable adapter is configured")


def write_scene_manifest(path: str | Path, manifest: dict[str, Any]) -> Path:
    return write_json(path, manifest)
