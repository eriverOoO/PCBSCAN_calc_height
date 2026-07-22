from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validation_harness.pbr import (
    BlenderCyclesBackend,
    PbrtBackendAdapter,
    blender_setup_message,
    build_scene_manifest,
    prepare_exact_22_patterns,
    write_scene_manifest,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render an exact 22-pattern L2 PCB case")
    parser.add_argument("--pattern-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--backend", choices=("blender_cycles", "pbrt"), default="blender_cycles")
    parser.add_argument("--blender", type=Path)
    parser.add_argument("--seed", type=int, default=3000)
    parser.add_argument("--manifest-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = args.output_root.expanduser().resolve()
    pattern_manifest = prepare_exact_22_patterns(args.pattern_root, output / "patterns")
    manifest = build_scene_manifest(
        pattern_manifest=pattern_manifest, seed=args.seed, backend=args.backend
    )
    manifest_path = write_scene_manifest(output / "scene_manifest.json", manifest)
    print(f"Scene manifest: {manifest_path}")
    if args.manifest_only:
        return 0
    backend = (
        BlenderCyclesBackend(args.blender) if args.backend == "blender_cycles" else PbrtBackendAdapter()
    )
    if not backend.available():
        print(blender_setup_message() if args.backend == "blender_cycles" else "PBRT backend is not configured")
        return 2
    backend.render(manifest_path, output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
