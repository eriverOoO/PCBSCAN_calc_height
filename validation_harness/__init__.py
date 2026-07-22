"""Validation-only infrastructure kept separate from the production decoder.

Ground truth is consumed by :mod:`validation_harness.metrics` and the report
stage only.  It must never be passed to ``pcb_fpp_decoder`` decode or
calibration inference APIs.
"""

from .manifests import (
    CALIBRATION_SEED_RANGE,
    HELD_OUT_SEED_RANGE,
    build_l0_manifest,
    load_config,
    resolve_validation_root,
    sha256_file,
)
from .metrics import evaluate_regions
from .ideal import IdealDatasetConfig, generate_ideal_dataset
from .stress import StressSynthesizer

__all__ = [
    "CALIBRATION_SEED_RANGE",
    "HELD_OUT_SEED_RANGE",
    "IdealDatasetConfig",
    "StressSynthesizer",
    "build_l0_manifest",
    "evaluate_regions",
    "generate_ideal_dataset",
    "load_config",
    "resolve_validation_root",
    "sha256_file",
]
