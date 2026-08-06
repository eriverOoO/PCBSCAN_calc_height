from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Mapping


# These are small sidecars that explain how a scan was captured or HDR-merged.
# Pattern images and exposure brackets intentionally stay in the input scan; copying
# them into every decode output would make the output unnecessarily large.
_VIEW_SIDECARS = (
    "scan_log.json",
    "quality_report.json",
    "hdr_merge_report.json",
    "hardware_capture_report.json",
    "blue_channel_histograms.png",
)
_SCAN_ROOT_SIDECARS = ("stage_precalibration.json",)


def preserve_capture_artifacts(
    views: Mapping[str | None, Path], output_dir: Path
) -> dict[str, object]:
    """Copy lightweight capture metadata into a self-contained decode output.

    ``None`` is used for a single-view decode and writes files directly under
    ``capture_logs/``.  Named views are used for a fused decode and are kept in
    separate subdirectories so identically named sidecars cannot overwrite each
    other.
    """
    root = Path(output_dir) / "capture_logs"
    root.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {"schema_version": 1, "views": {}}
    manifest_views: dict[str, object] = manifest["views"]  # type: ignore[assignment]

    root_sources: dict[Path, list[str]] = {}
    for view_name, raw_input_dir in views.items():
        input_dir = Path(raw_input_dir).expanduser().resolve()
        destination = root if view_name is None else root / view_name
        destination.mkdir(parents=True, exist_ok=True)
        copied = _copy_existing(_VIEW_SIDECARS, input_dir, destination)
        key = "input" if view_name is None else view_name
        manifest_views[key] = {
            "input_folder_name": input_dir.name,
            "copied_files": copied,
            "missing_files": [name for name in _VIEW_SIDECARS if name not in copied],
        }
        root_sources.setdefault(input_dir.parent, []).append(key)

    root_entries: list[dict[str, object]] = []
    for scan_root, view_names in root_sources.items():
        copied = _copy_existing(_SCAN_ROOT_SIDECARS, scan_root, root)
        if copied:
            root_entries.append(
                {
                    "scan_folder_name": scan_root.name,
                    "applies_to_views": view_names,
                    "copied_files": copied,
                }
            )
    manifest["scan_root_artifacts"] = root_entries

    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "directory": "capture_logs",
        "manifest": manifest_path.relative_to(output_dir).as_posix(),
        "views": manifest_views,
        "scan_root_artifacts": root_entries,
    }


def _copy_existing(names: tuple[str, ...], source_dir: Path, destination: Path) -> list[str]:
    copied: list[str] = []
    for name in names:
        source = source_dir / name
        if not source.is_file():
            continue
        target = destination / name
        shutil.copy2(source, target)
        copied.append(name)
    return copied
