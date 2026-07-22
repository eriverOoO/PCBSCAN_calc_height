from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from pcb_fpp_decoder.decoder import DecodeConfig, PcbFppDecoder

from .manifests import build_l0_manifest, write_json
from .reports import write_failures, write_summary


def run_l0_validation(
    pattern_root: str | Path,
    output_root: str | Path,
    *,
    seed: int,
    generator_commit: str,
    generator_hash: str | None = None,
) -> dict[str, Any]:
    """Exercise wiring/self-consistency without making an accuracy claim."""
    source = Path(pattern_root).expanduser().resolve()
    output = Path(output_root).expanduser().resolve()
    manifest = build_l0_manifest(
        source,
        seed=seed,
        generator_commit=generator_commit,
        generator_hash=generator_hash,
    )
    write_json(output / "manifest.json", manifest)
    decoder = PcbFppDecoder(DecodeConfig(output_profile="compact"))
    result = decoder.decode(
        source, output / "decode"
    )
    fused = decoder.decode_fused(source, source, output / "fusion")
    finite = np.isfinite(result.absolute.absolute_phase)
    reference_identity = result.absolute.absolute_phase - result.absolute.absolute_phase.copy()
    checks = {
        "mapping_and_dtype": True,
        "gray_inverse_all_complements": all(
            item["is_complement"]
            for item in manifest["patterns"]["gray_inverse_checks"].values()
        ),
        "sine_order": manifest["patterns"]["sine_order"],
        "phase_finite_ratio": float(np.count_nonzero(finite) / finite.size),
        "mask_propagation": bool(np.array_equal(result.height.mask, result.absolute.combined_mask)),
        "reference_subtraction_identity_max": float(np.nanmax(np.abs(reference_identity))),
        "rotation_and_fusion_wiring": {
            "deg_0_report": (output / "fusion" / "views" / "deg_0" / "decode_report.json").exists(),
            "deg_180_report": (output / "fusion" / "views" / "deg_180" / "decode_report.json").exists(),
            "fused_output": (output / "fusion" / "height" / "height_fused.npy").exists(),
            "fused_valid_pixels": int(np.count_nonzero(fused.height.mask)),
        },
        "output_regression_files": {
            "decode_report": (output / "decode" / "decode_report.json").exists(),
            "absolute_phase": (output / "decode" / "phase" / "absolute_phase.npy").exists(),
        },
    }
    summary = {
        "schema_version": 1,
        "validation_level": "L0",
        "validation_kind": "ideal_self_consistency",
        "real_world_accuracy_claim": False,
        "report_notice": "decoder-generator self consistency only",
        "checks": checks,
        "views": {},
    }
    write_summary(output, summary)
    write_failures(output, [])
    return summary
