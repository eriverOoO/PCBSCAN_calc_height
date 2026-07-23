from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Iterable


CATALOG = {
    "scanner_sim_physical": {
        "landing_page": "https://geometryprocessing.github.io/scanner-sim/",
        "metadata_api": None,
        "license": "CC BY 4.0",
        "estimated_min_bytes": 109_910_932,
        "purpose": "physical HDR image-domain audit and external geometry benchmark",
        "limitation": "47-pattern scanner and non-PCB scene; never rename as the production 22-pattern input",
        "sample_variants": [
            {
                "key": "img_40.exr",
                "size": 35_989_221,
                "url": "https://geometryprocessing.github.io/scanner-sim/data/img_40.exr",
                "checksum": "sha256:44deff2b483019fddf0fe13bf8dbdd7761c34b1cb4c6a7c0c42c8e50be3cd116",
            },
            {
                "key": "leo_010.exr",
                "size": 36_700_777,
                "url": "https://geometryprocessing.github.io/scanner-sim/data/leo_010.exr",
                "checksum": "sha256:2e1d7a41ec58d1a54f271d30371c3ad7de75697b027164072b02568b6c53025c",
            },
            {
                "key": "background.exr",
                "size": 37_220_934,
                "url": "https://geometryprocessing.github.io/scanner-sim/data/background.exr",
                "checksum": "sha256:48876cc06ece6c67fa8ed35b66327c0778c8bf75eab6f40631ec09d3b25aa4a9",
            },
        ],
    },
    "scanner_sim_calibration": {
        "landing_page": "https://archive.nyu.edu/handle/2451/63307",
        "metadata_api": None,
        "license": "CC BY 4.0",
        "estimated_min_bytes": 277_300_000,
        "purpose": "measured scanner calibration transfer: vignetting, projector response, and geometry",
        "limitation": (
            "calibration belongs to the scanner-sim rig, not the installed CS126MU rig; "
            "do not copy its values into production without a compatibility check"
        ),
        "sample_variants": [
            {
                "key": "camera_vignetting.zip",
                "size": 277_300_000,
                "url": "https://archive.nyu.edu/bitstream/2451/63307/3/camera_vignetting.zip",
                "checksum": None,
                "size_exact": False,
                "requires_checksum": True,
                "role": "measured camera flat-field/vignetting calibration",
            },
            {
                "key": "camera_intrinsics.zip",
                "size": 15_200_000_000,
                "url": "https://archive.nyu.edu/bitstream/2451/63307/2/camera_intrinsics.zip",
                "checksum": None,
                "size_exact": False,
                "requires_checksum": True,
                "role": "measured camera intrinsic/distortion calibration",
            },
            {
                "key": "projector_vignetting.zip",
                "size": 488_550_000,
                "url": "https://archive.nyu.edu/bitstream/2451/63307/7/projector_vignetting.zip",
                "checksum": None,
                "size_exact": False,
                "requires_checksum": True,
                "role": "measured projector spatial response/vignetting calibration",
            },
            {
                "key": "projector_intrinsics.zip",
                "size": 22_470_000_000,
                "url": "https://archive.nyu.edu/bitstream/2451/63307/5/projector_intrinsics.zip",
                "checksum": None,
                "size_exact": False,
                "requires_checksum": True,
                "role": "measured projector intrinsic/distortion calibration",
            },
            {
                "key": "projector_extrinsic.zip",
                "size": 7_490_000_000,
                "url": "https://archive.nyu.edu/bitstream/2451/63307/4/projector_extrinsic.zip",
                "checksum": None,
                "size_exact": False,
                "requires_checksum": True,
                "role": "measured camera-projector extrinsic calibration",
            },
            {
                "key": "projector_response.zip",
                "size": 8_760_000_000,
                "url": "https://archive.nyu.edu/bitstream/2451/63307/6/projector_response.zip",
                "checksum": None,
                "size_exact": False,
                "requires_checksum": True,
                "role": "measured projector radiometric response calibration",
            },
            {
                "key": "accuracy_test.zip",
                "size": 14_630_000_000,
                "url": "https://archive.nyu.edu/bitstream/2451/63307/1/accuracy_test.zip",
                "checksum": None,
                "size_exact": False,
                "requires_checksum": True,
                "role": "calibration-board accuracy test with known geometry",
            },
        ],
    },
    "scanner_sim_synthetic": {
        "landing_page": "https://archive.nyu.edu/handle/2451/63308",
        "metadata_api": None,
        "license": "CC BY 4.0",
        "estimated_min_bytes": 25_500_000,
        "purpose": "independent scanner-sim renderer with depth/mesh ground truth",
        "limitation": (
            "47-pattern non-PCB scenes; use only for external renderer/geometry checks, "
            "never as the production 22-frame input"
        ),
        "sample_variants": [
            {
                "key": "abc_objects.zip",
                "size": 25_500_000,
                "size_exact": False,
                "requires_checksum": True,
                "url": "https://archive.nyu.edu/bitstream/2451/63308/1/abc_objects.zip",
                "checksum": None,
                "role": "ABC source meshes",
            },
            {
                "key": "textured_objects.zip",
                "size": 508_430_000,
                "size_exact": False,
                "requires_checksum": True,
                "url": "https://archive.nyu.edu/bitstream/2451/63308/3/textured_objects.zip",
                "checksum": None,
                "role": "textured scan objects with GT assets",
            },
            {
                "key": "abc_scans.zip",
                "size": 41_460_000_000,
                "size_exact": False,
                "requires_checksum": True,
                "url": "https://archive.nyu.edu/bitstream/2451/63308/2/abc_scans.zip",
                "checksum": None,
                "role": "synthetic scans with depth/point-cloud/mesh GT",
            },
        ],
    },
    "gdd_physical": {
        "landing_page": "https://zenodo.org/records/12771948",
        "metadata_api": None,
        "license": "CC BY 4.0",
        "estimated_min_bytes": 13_800_000_000,
        "purpose": "real fringe/height-map external benchmark",
        "limitation": "different rig and patterns; target depth reaches 5 mm and is not a PCB/CS126MU substitute",
        "sample_variants": [
            {
                "key": "GDD_dataset_package.zip",
                "size": 13_800_000_000,
                "size_exact": False,
                "requires_checksum": True,
                "url": "https://zenodo.org/records/12771948/files/GDD_dataset_package.zip?download=1",
                "checksum": None,
                "role": "real fringe captures with calibrated height maps",
            }
        ],
    },
    "pbrt_zenodo": {
        "landing_page": "https://zenodo.org/records/17826191",
        "metadata_api": "https://zenodo.org/api/records/17826191",
        "license": "CC BY 4.0",
        "estimated_min_bytes": 2_100_000_000,
        "purpose": "submodule validation only: phase demodulation, unwrapping, masks/robustness",
        "limitation": "Gray + 6-step sine differs from the production exact 22-pattern sequence",
    },
    "fpp_ml_bench": {
        "landing_page": "https://huggingface.co/datasets/aharoon/fpp-ml-bench",
        "metadata_api": "https://huggingface.co/api/datasets/aharoon/fpp-ml-bench/tree/main?recursive=true&expand=false",
        "license": "MIT (re-check the dataset card at acquisition time)",
        "estimated_min_bytes": 2_000_000_000,
        "purpose": "external synthetic-domain test only",
        "limitation": "52 frames, matte materials, 960x960, 1.5-2.1 m; not a measured PCB substitute",
    },
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Explicit, resumable external FPP dataset fetcher")
    parser.add_argument("--dataset", choices=tuple(CATALOG), required=True)
    parser.add_argument("--variant", help="Exact remote file key/name; required for download")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("validation_data/external"),
        help="Destination root (default: validation_data/external)",
    )
    parser.add_argument("--url", help="Explicit archive URL when the catalog API cannot resolve the variant")
    parser.add_argument("--sha256", help="Expected SHA-256 (overrides catalog metadata)")
    parser.add_argument("--yes", action="store_true", help="Confirm the printed multi-GB transfer")
    parser.add_argument("--list-variants", action="store_true")
    parser.add_argument(
        "--sample-set",
        action="store_true",
        help="Download every small, checksum-pinned catalog sample (scanner_sim_physical only)",
    )
    parser.add_argument("--extract", action="store_true")
    return parser


def _metadata(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "pcb-fpp-validation/1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def _variants(dataset: str) -> list[dict[str, Any]]:
    if "sample_variants" in CATALOG[dataset]:
        return [dict(item) for item in CATALOG[dataset]["sample_variants"]]
    data = _metadata(CATALOG[dataset]["metadata_api"])
    variants: list[dict[str, Any]] = []
    if dataset == "pbrt_zenodo":
        for item in data.get("files", []):
            variants.append(
                {
                    "key": item.get("key"),
                    "size": int(item.get("size", 0)),
                    "url": item.get("links", {}).get("content"),
                    "checksum": item.get("checksum"),
                }
            )
    else:
        for item in data if isinstance(data, list) else []:
            if item.get("type") == "file":
                path = item.get("path")
                variants.append(
                    {
                        "key": path,
                        "size": int(item.get("size") or 0),
                        "url": f"https://huggingface.co/datasets/aharoon/fpp-ml-bench/resolve/main/{path}",
                        "checksum": None,
                    }
                )
    return variants


def _format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.2f} {unit}"
        value /= 1024
    return str(size)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _download(url: str, destination: Path, expected_size: int) -> Path:
    partial = destination.with_suffix(destination.suffix + ".part")
    offset = partial.stat().st_size if partial.exists() else 0
    headers = {"User-Agent": "pcb-fpp-validation/1"}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    request = urllib.request.Request(url, headers=headers)
    mode = "ab" if offset else "wb"
    with urllib.request.urlopen(request, timeout=60) as response, partial.open(mode) as handle:
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            handle.write(block)
    if expected_size and partial.stat().st_size != expected_size:
        raise IOError(
            f"download size mismatch: got {partial.stat().st_size}, expected {expected_size}"
        )
    partial.replace(destination)
    return destination


def _safe_targets(root: Path, names: Iterable[str]) -> None:
    base = root.resolve()
    for name in names:
        target = (root / name).resolve()
        try:
            target.relative_to(base)
        except ValueError as exc:
            raise ValueError(f"archive traversal blocked: {name}") from exc


def _extract(archive: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as bundle:
            _safe_targets(output, bundle.namelist())
            bundle.extractall(output)
        return
    if tarfile.is_tarfile(archive):
        with tarfile.open(archive) as bundle:
            members = bundle.getmembers()
            _safe_targets(output, (member.name for member in members))
            for member in members:
                if member.issym() or member.islnk():
                    raise ValueError(f"archive link blocked: {member.name}")
            bundle.extractall(output, members=members, filter="data")
        return
    raise ValueError(f"unsupported archive: {archive}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    catalog = CATALOG[args.dataset]
    print(f"Dataset: {args.dataset}")
    print(f"Source: {catalog['landing_page']}")
    print(f"License: {catalog['license']}")
    print(f"Use: {catalog['purpose']}")
    print(f"Limitation: {catalog['limitation']}")
    if os.environ.get("CI"):
        raise SystemExit("Automatic external dataset download is disabled in CI")

    variants = _variants(args.dataset)
    if args.list_variants:
        for item in variants:
            print(f"{item['key']}\t{_format_size(item['size'])}")
        return 0
    if args.sample_set:
        if args.dataset != "scanner_sim_physical":
            raise SystemExit("--sample-set is currently supported only for scanner_sim_physical")
        if args.variant or args.url or args.sha256 or args.extract:
            raise SystemExit(
                "--sample-set cannot be combined with --variant/--url/--sha256/--extract"
            )
        if not args.yes:
            raise SystemExit(
                "Download not started. Re-run with --yes after reviewing size/license."
            )
        root = args.output_root.expanduser().resolve() / args.dataset
        root.mkdir(parents=True, exist_ok=True)
        records: list[dict[str, Any]] = []
        for selected in variants:
            destination = root / Path(selected["key"]).name
            expected_checksum = str(selected["checksum"]).split(":", 1)[-1]
            if destination.exists() and _sha256(destination) == expected_checksum:
                print(f"Already verified: {destination}")
            else:
                _download(selected["url"], destination, int(selected["size"]))
            actual = _sha256(destination)
            if actual != expected_checksum:
                raise IOError(
                    f"SHA-256 mismatch for {destination}: {actual} != {expected_checksum}"
                )
            records.append(
                {
                    "variant": selected["key"],
                    "download_url": selected["url"],
                    "size_bytes": destination.stat().st_size,
                    "sha256": actual,
                }
            )
        provenance = {
            "dataset": args.dataset,
            "source": catalog["landing_page"],
            "license": catalog["license"],
            "purpose": catalog["purpose"],
            "limitation": catalog["limitation"],
            "files": records,
        }
        (root / "LICENSE_AND_CITATION.json").write_text(
            json.dumps(provenance, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Saved and verified sample set: {root}")
        return 0
    if not args.variant:
        raise SystemExit("--variant is required; use --list-variants first")
    item = next((candidate for candidate in variants if candidate["key"] == args.variant), None)
    if item is None and not args.url:
        raise SystemExit(f"variant not found in dataset metadata: {args.variant}")
    url = args.url or item["url"]
    size = int(item["size"] if item else catalog["estimated_min_bytes"])
    checksum = args.sha256 or (item.get("checksum") if item else None)
    if checksum and checksum.startswith("sha256:"):
        checksum = checksum.split(":", 1)[1]
    if item and item.get("requires_checksum") and not checksum:
        raise SystemExit(
            "This calibration archive has no catalog checksum. Re-run with an explicit "
            "--sha256 after independently verifying the archive hash."
        )
    print(f"Selected variant: {args.variant}")
    print(f"Expected transfer: {_format_size(size)}")
    if not args.yes:
        raise SystemExit("Download not started. Re-run with --yes after reviewing size/license.")

    root = args.output_root.expanduser().resolve() / args.dataset
    root.mkdir(parents=True, exist_ok=True)
    destination = root / Path(args.variant).name
    _download(url, destination, size if (item or {}).get("size_exact", True) else 0)
    actual = _sha256(destination)
    if checksum and actual.lower() != checksum.lower():
        raise IOError(f"SHA-256 mismatch for {destination}: {actual} != {checksum}")
    provenance = {
        "dataset": args.dataset,
        "variant": args.variant,
        "source": catalog["landing_page"],
        "download_url": url,
        "license": catalog["license"],
        "purpose": catalog["purpose"],
        "limitation": catalog["limitation"],
        "size_bytes": destination.stat().st_size,
        "sha256": actual,
        "size_check": "exact" if (item or {}).get("size_exact", True) else "not_pinned_catalog_estimate",
    }
    (root / "LICENSE_AND_CITATION.json").write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if args.extract:
        _extract(destination, root / "extracted" / destination.stem)
    print(f"Saved and verified: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
