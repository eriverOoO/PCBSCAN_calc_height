from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SUPPORTED_EXTERNAL_DATASETS = {
    "scanner_sim_physical": {
        "expected_sequence": "47-pattern physical HDR structured-light scan",
        "allowed_validation_scope": [
            "real_image_domain_audit",
        ],
        "production_22_frame_compatible": False,
        "license": "CC BY 4.0",
        "evidence_class": "peer_reviewed_physical_capture_no_independent_gt",
        "ground_truth_available": False,
        "archive": "https://archive.nyu.edu/handle/2451/63306",
        "calibration_archive": "https://archive.nyu.edu/handle/2451/63307",
    },
    "scanner_sim_calibration": {
        "expected_sequence": "scanner-sim physical calibration archives",
        "allowed_validation_scope": [
            "measured_vignetting_transfer",
            "measured_projector_response_transfer",
            "calibration_workflow_reference",
        ],
        "production_22_frame_compatible": False,
        "license": "CC BY 4.0",
        "evidence_class": "peer_reviewed_measured_calibration_other_rig",
        "ground_truth_available": False,
        "source": "https://archive.nyu.edu/handle/2451/63307",
        "transfer_policy": (
            "only apply an extracted field/response after recording archive hash, "
            "source rig, and compatibility review"
        ),
    },
    "scanner_sim_synthetic": {
        "expected_sequence": "scanner-sim synthetic 47-pattern HDR/LDR sequence",
        "allowed_validation_scope": ["external_geometry_benchmark", "renderer_cross_check"],
        "production_22_frame_compatible": False,
        "license": "CC BY 4.0",
        "evidence_class": "peer_reviewed_independent_renderer_with_depth_mesh_gt",
        "ground_truth_available": True,
        "source": "https://archive.nyu.edu/handle/2451/63308",
    },
    "pbrt_zenodo": {
        "expected_sequence": "Gray code plus 6-step sine",
        "allowed_validation_scope": ["phase_demodulation", "unwrapping", "mask_robustness"],
        "production_22_frame_compatible": False,
    },
    "fpp_ml_bench": {
        "expected_sequence": "52-frame sequence",
        "allowed_validation_scope": ["external_synthetic_domain"],
        "production_22_frame_compatible": False,
        "license": "MIT",
        "evidence_class": "independent_physics_renderer_with_object_held_out_split",
    },
    "hdr_net_real": {
        "expected_sequence": "real HDR FPP scenes with multi-exposure reference",
        "allowed_validation_scope": ["real_hdr_image_domain_audit"],
        "production_22_frame_compatible": False,
        "license": "dataset terms must be verified separately from MIT code",
        "evidence_class": "peer_reviewed_real_capture_license_pending",
    },
    "3dlf_scan": {
        "expected_sequence": "structured-light depth/point cloud and reference meshes",
        "allowed_validation_scope": ["external_geometry_benchmark"],
        "production_22_frame_compatible": False,
        "license": "verify the archived dataset record before download",
        "evidence_class": "published_multi_sensor_physical_scan",
    },
    "gdd_physical": {
        "expected_sequence": "real fringe images with calibrated physical height maps",
        "allowed_validation_scope": ["external_real_capture_height_benchmark"],
        "production_22_frame_compatible": False,
        "license": "CC BY 4.0",
        "evidence_class": "peer_reviewed_physical_fpp_with_height_map",
        "ground_truth_available": True,
        "source": "https://zenodo.org/records/12771948",
        "limitation": "different rig/resolution/patterns and up to 5 mm target depth; not a CS126MU PCB substitute",
    },
    "sk3d": {
        "expected_sequence": "real RGB/IR views with registered structured-light reference meshes",
        "allowed_validation_scope": ["external_geometry_benchmark"],
        "production_22_frame_compatible": False,
        "license": "verify dataset terms separately from MIT code",
        "evidence_class": "published_physical_scan_with_reference_mesh",
        "ground_truth_available": True,
        "source": "https://github.com/Skoltech-3D/sk3d_data",
        "limitation": "no production fringe sequence and no PCB-specific height GT",
    },
    "pcb_dslr": {
        "expected_sequence": "real polarized PCB appearance images",
        "allowed_validation_scope": ["held_out_pcb_appearance"],
        "production_22_frame_compatible": False,
        "license": "CC BY 4.0 (verify record terms at acquisition)",
        "evidence_class": "held_out_real_pcb_appearance_only",
        "ground_truth_available": False,
        "source": "https://zenodo.org/records/3886553",
        "limitation": "no projector patterns or metric 3D height; do not use for height accuracy",
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
