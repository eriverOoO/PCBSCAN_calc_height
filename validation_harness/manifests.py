from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from PIL import Image


CALIBRATION_SEED_RANGE = range(1000, 1100)
HELD_OUT_SEED_RANGE = range(2000, 2100)
PATTERN_IDS = tuple(range(22))


def resolve_validation_root(value: str | Path | None = None) -> Path:
    """Resolve data root without embedding a user-specific absolute path."""
    raw = value if value is not None else os.environ.get("PCB_FPP_VALIDATION_ROOT")
    if raw is None:
        raw = Path.cwd() / "validation_data"
    return Path(raw).expanduser().resolve()


def load_config(path: str | Path) -> dict[str, Any]:
    """Load JSON-compatible YAML, with PyYAML support when it is installed."""
    config_path = Path(path)
    text = config_path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise ValueError(
                f"{config_path} is not JSON-compatible YAML; install PyYAML for general YAML"
            ) from exc
        data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"validation config must contain a mapping: {config_path}")
    return data


def write_json(path: str | Path, payload: Mapping[str, Any]) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return output


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_array(array: np.ndarray) -> str:
    arr = np.ascontiguousarray(array)
    digest = hashlib.sha256()
    digest.update(arr.dtype.str.encode("ascii"))
    digest.update(str(arr.shape).encode("ascii"))
    digest.update(arr.tobytes())
    return digest.hexdigest()


def pattern_files(root: str | Path) -> dict[int, Path]:
    folder = Path(root)
    mapping: dict[int, Path] = {}
    for pattern_id in PATTERN_IDS:
        candidates = sorted(folder.glob(f"pattern_{pattern_id:03d}.*"))
        if candidates:
            mapping[pattern_id] = candidates[0]
    return mapping


def inspect_pattern_sequence(root: str | Path, require_22: bool = True) -> dict[str, Any]:
    mapping = pattern_files(root)
    expected = PATTERN_IDS if require_22 else tuple(range(14))
    missing = [pattern_id for pattern_id in expected if pattern_id not in mapping]
    if missing:
        raise FileNotFoundError(f"missing pattern ids in {root}: {missing}")

    shapes: set[tuple[int, ...]] = set()
    dtypes: set[str] = set()
    hashes: dict[str, str] = {}
    inverse_checks: dict[str, dict[str, float | bool]] = {}
    arrays: dict[int, np.ndarray] = {}
    for pattern_id, path in sorted(mapping.items()):
        with Image.open(path) as image:
            arr = np.asarray(image)
        arrays[pattern_id] = arr
        shapes.add(tuple(int(value) for value in arr.shape))
        dtypes.add(str(arr.dtype))
        hashes[str(pattern_id)] = sha256_file(path)
    if len(shapes) != 1:
        raise ValueError(f"pattern image shape mismatch: {sorted(shapes)}")
    if len(dtypes) != 1:
        raise ValueError(f"pattern dtype mismatch: {sorted(dtypes)}")

    if require_22:
        max_value = float(np.iinfo(arrays[0].dtype).max) if np.issubdtype(
            arrays[0].dtype, np.integer
        ) else 1.0
        captured_pair_sum = arrays[0].astype(np.float64) + arrays[1].astype(np.float64)
        for source, inverse in zip(range(2, 10), range(14, 22)):
            residual = arrays[source].astype(np.float64) + arrays[inverse].astype(np.float64)
            digital_error = float(np.mean(np.abs(residual - max_value)))
            captured_error = float(np.mean(np.abs(residual - captured_pair_sum)))
            relation = (
                "digital_complement"
                if digital_error <= captured_error
                else "captured_pair_sum_white_black"
            )
            mean_error = min(digital_error, captured_error)
            inverse_checks[f"{source}:{inverse}"] = {
                "mean_complement_error": mean_error,
                "is_complement": mean_error <= max(1.0, max_value / 255.0),
                "relation": relation,
            }

    return {
        "pattern_count": len(mapping),
        "mapping": {str(key): value.name for key, value in sorted(mapping.items())},
        "pattern_sha256": hashes,
        "dtype": next(iter(dtypes)),
        "image_shape": list(next(iter(shapes))),
        "gray_inverse_checks": inverse_checks,
        "sine_order": [10, 11, 12, 13],
    }


def build_l0_manifest(
    pattern_root: str | Path,
    *,
    seed: int,
    generator_commit: str,
    generator_hash: str | None = None,
) -> dict[str, Any]:
    inspection = inspect_pattern_sequence(pattern_root, require_22=True)
    return {
        "schema_version": 1,
        "validation_level": "L0",
        "validation_kind": "ideal_self_consistency",
        "real_world_accuracy_claim": False,
        "report_notice": "decoder-generator self consistency only",
        "generator": {
            "commit": generator_commit,
            "hash": generator_hash or generator_commit,
            "seed": int(seed),
        },
        "patterns": inspection,
    }


def output_hashes(root: str | Path) -> dict[str, str]:
    folder = Path(root)
    return {
        path.relative_to(folder).as_posix(): sha256_file(path)
        for path in sorted(folder.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    }


def assert_seed_partition(seed: int, partition: str) -> None:
    allowed: Sequence[int]
    if partition == "calibration":
        allowed = CALIBRATION_SEED_RANGE
    elif partition == "held_out":
        allowed = HELD_OUT_SEED_RANGE
    else:
        raise ValueError("partition must be 'calibration' or 'held_out'")
    if seed not in allowed:
        raise ValueError(f"seed {seed} is outside the {partition} range")
