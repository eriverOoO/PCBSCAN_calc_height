from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SUPPORTED_EXTERNAL_DATASETS = {
    "pbrt_zenodo": {
        "expected_sequence": "Gray code plus 6-step sine",
        "allowed_validation_scope": ["phase_demodulation", "unwrapping", "mask_robustness"],
        "production_22_frame_compatible": False,
    },
    "fpp_ml_bench": {
        "expected_sequence": "52-frame sequence",
        "allowed_validation_scope": ["external_synthetic_domain"],
        "production_22_frame_compatible": False,
    },
}


def build_external_adapter_manifest(dataset: str, source_root: str | Path) -> dict[str, Any]:
    if dataset not in SUPPORTED_EXTERNAL_DATASETS:
        raise ValueError(f"unsupported external dataset: {dataset}")
    policy = SUPPORTED_EXTERNAL_DATASETS[dataset]
    return {
        "schema_version": 1,
        "validation_level": "external",
        "dataset": dataset,
        "source_root": str(Path(source_root).expanduser().resolve()),
        "sequence_adapter": "submodule_only",
        "rename_as_production_22_frame_sequence": False,
        **policy,
    }


def write_external_adapter_manifest(
    dataset: str, source_root: str | Path, output_path: str | Path
) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            build_external_adapter_manifest(dataset, source_root),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return output
