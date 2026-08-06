"""Auditable contract for a hardware-synchronised FPP capture.

The projector/camera controller is intentionally outside this decoder package.
It must write the fields checked here after each exposure.  A log can therefore
prove that a decode used a locked pattern sequence, rather than merely claiming
that it did.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


CONTRACT_VERSION = 1
REQUIRED_CAMERA_SETTINGS = {
    "auto_exposure": False,
    "auto_gain": False,
    "auto_white_balance": False,
    "gamma_enabled": False,
    "output_linear": True,
}
_IMAGE_KEYS = {
    "file",
    "filename",
    "path",
    "image",
    "image_path",
    "relative_path",
    "received_image_filename",
    "received_image_relative_path",
}


def load_capture_log(input_dir: Path) -> dict[str, Any] | None:
    path = Path(input_dir) / "scan_log.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {"entries": data}


def audit_capture_contract(
    input_dir: Path,
    required_pattern_ids: Iterable[int] = range(14),
) -> dict[str, Any]:
    """Validate controller evidence without pretending to inspect GPIO state.

    A passing result means that the capture controller declared and recorded the
    required hardware-triggered sequence.  The resulting report deliberately
    distinguishes missing evidence from a proven optical failure.
    """

    root = Path(input_dir).expanduser().resolve()
    required = sorted({int(value) for value in required_pattern_ids})
    report: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "input_dir": str(root),
        "required_pattern_ids": required,
        "status": "rejected",
        "errors": [],
        "warnings": [],
        "evidence": {},
    }
    errors: list[str] = report["errors"]
    warnings: list[str] = report["warnings"]

    try:
        data = load_capture_log(root)
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"scan_log.json cannot be read: {exc}")
        return report
    if data is None:
        errors.append("scan_log.json is required for a hardware-trigger audit.")
        return report

    protocol = _mapping(data.get("capture_protocol"))
    settings = _mapping(data.get("settings"))
    camera = _mapping(data.get("camera"))
    report["evidence"] = {
        "scan_id": data.get("scan_id"),
        "status": data.get("status"),
        "capture_protocol": protocol,
        "camera": camera,
        "settings": settings,
    }

    if data.get("status") != "ok":
        errors.append("scan_log status must be 'ok' for a strict decode.")
    if data.get("capture_contract_version") != CONTRACT_VERSION:
        errors.append(
            f"capture_contract_version must be {CONTRACT_VERSION}; "
            f"got {data.get('capture_contract_version')!r}."
        )
    if protocol.get("sequence_locked") is not True:
        errors.append("capture_protocol.sequence_locked must be true.")
    if protocol.get("projector_pattern_advance") != "hardware_trigger":
        errors.append("projector pattern advance must be declared as hardware_trigger.")
    if protocol.get("camera_exposure") != "hardware_trigger":
        errors.append("camera exposure must be declared as hardware_trigger.")
    if not isinstance(protocol.get("trigger_source"), str) or not protocol["trigger_source"].strip():
        errors.append("capture_protocol.trigger_source must identify the shared trigger line.")
    _check_camera_settings(settings, camera, errors, warnings)

    entries = _flatten_pattern_entries(data)
    by_id: dict[int, list[dict[str, Any]]] = {}
    for entry in entries:
        pattern_id = _pattern_id(entry)
        if pattern_id is not None:
            by_id.setdefault(pattern_id, []).append(entry)

    missing = [pattern_id for pattern_id in required if pattern_id not in by_id]
    duplicates = [pattern_id for pattern_id in required if len(by_id.get(pattern_id, [])) != 1]
    if missing:
        errors.append(f"missing trigger records for required pattern ids: {missing}.")
    if duplicates:
        errors.append(f"required pattern ids must have exactly one trigger record: {duplicates}.")

    observed_sequence: list[int] = []
    trigger_ids: list[Any] = []
    invalid_rows: list[int] = []
    for pattern_id in required:
        rows = by_id.get(pattern_id, [])
        if len(rows) != 1:
            continue
        row = rows[0]
        if not _has_image_reference(row):
            invalid_rows.append(pattern_id)
        sequence_index = row.get("sequence_index")
        if not isinstance(sequence_index, int):
            invalid_rows.append(pattern_id)
        else:
            observed_sequence.append(sequence_index)
        trigger_id = row.get("trigger_id")
        if trigger_id in (None, ""):
            invalid_rows.append(pattern_id)
        else:
            trigger_ids.append(trigger_id)
    if invalid_rows:
        errors.append(
            "each required trigger record needs filename, sequence_index, and trigger_id; "
            f"invalid pattern ids: {sorted(set(invalid_rows))}."
        )
    if observed_sequence and observed_sequence != list(range(len(required))):
        errors.append(
            f"sequence_index must be contiguous 0..{len(required) - 1}; got {observed_sequence}."
        )
    if len(trigger_ids) != len(set(trigger_ids)):
        errors.append("trigger_id values must be unique for every required pattern.")

    report["evidence"].update(
        {
            "pattern_record_count": len(entries),
            "required_pattern_record_count": sum(len(by_id.get(pattern_id, [])) for pattern_id in required),
            "observed_sequence_indices": observed_sequence,
            "missing_pattern_ids": missing,
        }
    )
    if not errors:
        report["status"] = "passed"
    return report


def write_capture_contract_report(input_dir: Path, output_path: Path) -> dict[str, Any]:
    report = audit_capture_contract(input_dir)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def _check_camera_settings(
    settings: dict[str, Any], camera: dict[str, Any], errors: list[str], warnings: list[str]
) -> None:
    source = {**camera, **settings}
    for key, expected in REQUIRED_CAMERA_SETTINGS.items():
        if source.get(key) is not expected:
            errors.append(f"{key} must be {expected!r}; got {source.get(key)!r}.")
    if source.get("exposure_mode") != "manual":
        errors.append("exposure_mode must be 'manual'.")
    if source.get("gain_mode") != "manual":
        errors.append("gain_mode must be 'manual'.")
    if source.get("focus_mode") != "manual":
        errors.append("focus_mode must be 'manual'.")
    pixel_format = source.get("pixel_format")
    if not isinstance(pixel_format, str) or not pixel_format.lower().startswith("mono"):
        errors.append("pixel_format must be a linear Mono format such as Mono8, Mono12, or Mono16.")
    if source.get("white_balance_supported") is True:
        warnings.append("white_balance_supported is true; verify auto_white_balance stayed disabled.")


def _flatten_pattern_entries(data: Any) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if isinstance(data, dict):
        if _pattern_id(data) is not None and any(key in data for key in _IMAGE_KEYS):
            entries.append(data)
        for value in data.values():
            entries.extend(_flatten_pattern_entries(value))
    elif isinstance(data, list):
        for value in data:
            entries.extend(_flatten_pattern_entries(value))
    return entries


def _pattern_id(entry: dict[str, Any]) -> int | None:
    for key in ("pattern_id", "patternId", "pattern", "id", "index"):
        try:
            value = int(entry[key])
        except (KeyError, TypeError, ValueError):
            continue
        if value >= 0:
            return value
    return None


def _has_image_reference(entry: dict[str, Any]) -> bool:
    return any(isinstance(entry.get(key), str) and entry[key] for key in _IMAGE_KEYS)


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
