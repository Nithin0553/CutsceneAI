"""Read-only Unreal project intelligence probe for adaptive CutSceneAI mapping."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import unreal

import unreal_compat


def _evidence(evidence_id: str, source: str, value: Any, path: str = "") -> dict[str, Any]:
    item: dict[str, Any] = {
        "evidence_id": evidence_id,
        "source": source,
        "value": value,
        "confidence": 1.0,
    }
    if path:
        item["path"] = path
    return item


def _project_file() -> Path | None:
    paths = getattr(unreal, "Paths", None)
    getter = getattr(paths, "get_project_file_path", None) if paths else None
    if not callable(getter):
        return None
    try:
        value = str(getter())
    except Exception:
        return None
    if not value:
        return None
    return Path(value)


def _project_fingerprint(project_file: Path | None) -> str:
    digest = hashlib.sha256()
    digest.update(unreal_compat.engine_version().encode("utf-8"))
    if project_file is not None:
        digest.update(str(project_file.resolve()).encode("utf-8"))
        try:
            digest.update(project_file.read_bytes())
        except OSError:
            pass
    return digest.hexdigest()


def _project_plugins(project_file: Path | None) -> list[str]:
    if project_file is None:
        return []
    try:
        data = json.loads(project_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    result: list[str] = []
    for item in data.get("Plugins", []):
        if not isinstance(item, dict) or not item.get("Enabled", False):
            continue
        name = str(item.get("Name", "")).strip()
        if name:
            result.append(name)
    return sorted(set(result))


def _supports_rotator_semantic_fields() -> bool:
    try:
        value = unreal_compat.make_rotator_semantic(roll=1.0, pitch=2.0, yaw=3.0)
        return (
            abs(float(value.roll) - 1.0) < 1e-6
            and abs(float(value.pitch) - 2.0) < 1e-6
            and abs(float(value.yaw) - 3.0) < 1e-6
        )
    except Exception:
        return False


def analyze_project() -> dict[str, Any]:
    """Return a Project Intelligence Profile without modifying project content."""
    project_file = _project_file()
    engine_version = unreal_compat.engine_version()
    profile_id = "unreal:" + _project_fingerprint(project_file)[:24]

    rotator_fields = _supports_rotator_semantic_fields()
    root_sampling = unreal_compat.animation_root_sampling_strategy()
    has_root_sampling = root_sampling != "unavailable"
    has_completion = getattr(unreal, "MovieSceneCompletionMode", None) is not None
    section_type = getattr(unreal, "MovieSceneSkeletalAnimationSection", None)
    has_post_roll = bool(
        section_type is not None
        and (
            callable(getattr(section_type, "set_post_roll_frames", None))
            or hasattr(section_type, "post_roll_frames")
        )
    )

    evidence = [
        _evidence("target.engine_version", "unreal.SystemLibrary", engine_version),
        _evidence(
            "target.rotation_semantics",
            "runtime.capability_probe",
            {
                "semantic_fields": ["roll", "pitch", "yaw"],
                "named_field_construction": rotator_fields,
            },
        ),
        _evidence(
            "target.coordinate_basis",
            "engine_contract",
            {
                "handedness": "LEFT_HANDED",
                "up_axis": "+Z",
                "forward_axis": "+X",
                "right_axis": "+Y",
                "linear_unit": "CENTIMETER",
            },
        ),
        _evidence(
            "target.camera_basis",
            "engine_contract",
            {"forward_axis": "+X", "up_axis": "+Z", "roll_axis": "+X"},
        ),
        _evidence(
            "target.camera_lens_model",
            "runtime.capability_probe",
            {
                "cine_camera": getattr(unreal, "CineCameraComponent", None) is not None,
                "generic_camera": getattr(unreal, "CameraComponent", None) is not None,
            },
        ),
        _evidence(
            "target.section_completion_capabilities",
            "runtime.capability_probe",
            {"completion_mode": has_completion, "post_roll": has_post_roll},
        ),
    ]

    capabilities = [
        {
            "id": "rotator.semantic_fields",
            "state": "SUPPORTED" if rotator_fields else "UNSUPPORTED",
            "details": {"construction": "named_fields"},
            "evidence_ids": ["target.rotation_semantics"],
        },
        {
            "id": "camera.forward_up_basis",
            "state": "SUPPORTED",
            "details": {"forward_axis": "+X", "up_axis": "+Z"},
            "evidence_ids": ["target.camera_basis"],
        },
        {
            "id": "camera.lens_model",
            "state": "SUPPORTED"
            if getattr(unreal, "CameraComponent", None) is not None
            else "UNSUPPORTED",
            "details": {},
            "evidence_ids": ["target.camera_lens_model"],
        },
        {
            "id": "animation.root_motion_sampling",
            "state": "SUPPORTED" if has_root_sampling else "UNSUPPORTED",
            "details": {"strategy": root_sampling},
            "evidence_ids": [],
        },
        {
            "id": "sequencer.section_completion",
            "state": "SUPPORTED" if has_completion else "UNSUPPORTED",
            "details": {},
            "evidence_ids": ["target.section_completion_capabilities"],
        },
        {
            "id": "sequencer.post_roll",
            "state": "SUPPORTED" if has_post_roll else "UNSUPPORTED",
            "details": {},
            "evidence_ids": ["target.section_completion_capabilities"],
        },
    ]

    return {
        "profile_version": "0.1.0",
        "profile_id": profile_id,
        "engine": {
            "name": "unreal",
            "version": engine_version,
            "build": engine_version,
            "adapter_name": "cutsceneai.unreal",
            "adapter_version": "0.2.0-dev",
        },
        "project": {
            "fingerprint": _project_fingerprint(project_file),
            "project_ref": str(project_file) if project_file else "",
            "plugins": _project_plugins(project_file),
            "packages": [],
        },
        "conventions": {
            "coordinate_system": {
                "handedness": "LEFT_HANDED",
                "up_axis": "+Z",
                "forward_axis": "+X",
                "right_axis": "+Y",
                "linear_unit": "CENTIMETER",
            },
            "rotation": {
                "representation": "ROTATOR_DEGREES",
                "semantic_fields": ["roll", "pitch", "yaw"],
                "constructor_argument_order": ["roll", "pitch", "yaw"],
                "positive_rotation_notes": "Use semantic fields; never rely on positional binding order.",
            },
            "camera": {
                "fov_axis": "physical_lens",
                "forward_axis": "+X",
                "up_axis": "+Z",
                "roll_semantics": "roll around forward +X",
                "aspect_provenance": "transfer_output_gate",
            },
            "animation": {
                "root_motion_space": "target_import_space",
                "root_motion_forward_axis": "measured_per_asset",
                "section_completion_model": "MovieScene completion + pre/post-roll",
            },
            "timing": {},
            "render": {},
        },
        "capabilities": capabilities,
        "settings": {
            "runtime_profile": unreal_compat.runtime_profile(),
        },
        "evidence": evidence,
    }


def write_profile(path: str) -> dict[str, Any]:
    profile = analyze_project()
    Path(path).write_text(json.dumps(profile, indent=2), encoding="utf-8")
    unreal.log(f"[CutSceneAI] Project intelligence profile written: {path}")
    return profile
