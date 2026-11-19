"""Read-only, independent Unreal 5.8 AnimSequence bone-key verification.

Run this only in a *different* Unreal Editor process after the approved pose
writer has saved its asset. It reads the saved asset's native animation data,
never edits or loads it into a Sequencer, and never certifies rendered fidelity.
All unavailable APIs, missing keys, stale evidence and project mismatches
fail closed. The original native write receipt is immutable.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path

from studio_skeletal_pose_bake import _class, _path, _read_bake


class NativePoseReadbackError(RuntimeError):
    pass


def _source_file(path, *, limit=16 * 1024 * 1024):
    file = Path(path)
    if file.is_symlink() or any(parent.is_symlink() for parent in file.parents):
        raise NativePoseReadbackError("Readback evidence cannot pass through symlinks.")
    if not file.is_file() or not 0 < file.stat().st_size <= limit:
        raise NativePoseReadbackError("Readback evidence is missing or exceeds the file budget.")
    return file


def _json(path):
    try:
        value = json.loads(_source_file(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, UnicodeError) as error:
        raise NativePoseReadbackError("Native write receipt is not valid JSON.") from error
    if not isinstance(value, dict):
        raise NativePoseReadbackError("Native write receipt must be an object.")
    return value


def _float(value, label):
    if type(value) not in (float, int) or not math.isfinite(value):
        raise NativePoseReadbackError("Nonfinite or nonnumeric native " + label)
    return float(value)


def _components(value, size, label):
    axes = ("x", "y", "z", "w")[:size]
    try:
        return tuple(_float(getattr(value, axis), label) for axis in axes)
    except AttributeError as error:
        raise NativePoseReadbackError("Native " + label + " has missing components.") from error


def _angle(a, b):
    alen = math.sqrt(sum(x * x for x in a))
    blen = math.sqrt(sum(x * x for x in b))
    if abs(alen - 1.0) > 0.02 or abs(blen - 1.0) > 0.02:
        raise NativePoseReadbackError("Native bone quaternion is not normalized.")
    dot = min(1.0, abs(sum(x * y for x, y in zip(a, b)) / (alen * blen)))
    return math.degrees(2 * math.acos(dot))


def _rate(model):
    try:
        rate = model.get_editor_property("frame_rate")
        numerator = rate.numerator
        denominator = rate.denominator
    except (AttributeError, TypeError, RuntimeError) as error:
        raise NativePoseReadbackError("Native animation data model frame rate is unavailable.") from error
    if (type(numerator) is not int or type(denominator) is not int
            or numerator <= 0 or denominator <= 0):
        raise NativePoseReadbackError("Native animation frame rate is invalid.")
    return (numerator, denominator)


def verify(pose_bake_path, write_receipt_path, output_path, *, api=None,
           position_tolerance_cm=0.02, rotation_tolerance_degrees=0.2,
           scale_tolerance=0.0001):
    """Compare the fully saved native raw tracks with an approved immutable bake.

    This is a readback verification of exact *native track key data*, not an
    animation evaluation, skin deformation or full cutscene fidelity result.
    """
    output = Path(output_path)
    if (output.exists() or output.is_symlink() or not output.parent.is_dir()
            or any(parent.is_symlink() for parent in output.parents)):
        raise NativePoseReadbackError("Readback result requires a new, non-symlinked output file.")
    for tolerance in (position_tolerance_cm, rotation_tolerance_degrees, scale_tolerance):
        if type(tolerance) not in (float, int) or not math.isfinite(tolerance) or tolerance <= 0:
            raise NativePoseReadbackError("Readback tolerances must be positive and finite.")

    baked = _read_bake(_source_file(pose_bake_path, limit=256 * 1024 * 1024))
    receipt = _json(write_receipt_path)
    target = baked["target"]
    if (receipt.get("kind") != "cutsceneai.studio.native_skeletal_pose_bake_receipt"
            or receipt.get("schema_version") != "1"
            or receipt.get("status") != "NATIVE_SAVED_PENDING_INDEPENDENT_READBACK"
            or receipt.get("native_asset_writes_possible") is not True
            or receipt.get("fidelity_verified") is not False
            or receipt.get("native_target_readback_verified") is not False
            or receipt.get("source_sha256") != hashlib.sha256(
                Path(pose_bake_path).read_bytes()).hexdigest()
            or receipt.get("source_entity_id") != baked["source_entity_id"]
            or receipt.get("target_project_identity_sha256")
            != target["unreal_project_identity_sha256"]
            or receipt.get("target_skeleton_asset_path") != target["skeleton_asset_path"]
            or receipt.get("target_animation_asset_path") != target["animation_asset_path"]
            or receipt.get("saved_bone_count") != len(baked["bone_tracks"])
            or receipt.get("saved_key_count_per_bone") != baked["sampled_keys"]):
        raise NativePoseReadbackError("Saved native write receipt is incomplete, stale or not eligible.")
    writer_pid = receipt.get("generation_editor_pid")
    if type(writer_pid) is not int or writer_pid <= 0 or writer_pid == os.getpid():
        raise NativePoseReadbackError("Independent readback requires a different Unreal Editor process.")

    if api is None:
        import unreal as api
    project = Path(api.Paths.get_project_file_path()).resolve()
    if not project.is_file() or project.is_symlink():
        raise NativePoseReadbackError("Unreal project file is missing or unsafe.")
    project_identity = hashlib.sha256(
        str(project).encode("utf-8") + b"\0" + project.read_bytes()
    ).hexdigest()
    if project_identity != target["unreal_project_identity_sha256"]:
        raise NativePoseReadbackError("Reopened Unreal project differs from approved target.")
    if not str(api.SystemLibrary.get_engine_version()).startswith("5.8."):
        raise NativePoseReadbackError("Readback requires Unreal 5.8.")
    library = getattr(api, "AnimationLibrary", None)
    if not all(callable(getattr(library, name, None))
               for name in ("get_raw_track_data", "get_num_frames", "get_num_keys")):
        raise NativePoseReadbackError("Native raw animation readback APIs unavailable.")

    asset = api.load_asset(target["animation_asset_path"])
    if _class(asset) != "AnimSequence" or _path(asset) != target["animation_asset_path"]:
        raise NativePoseReadbackError("Saved native animation asset missing or wrong class.")
    if _path(asset.get_editor_property("skeleton")) != target["skeleton_asset_path"]:
        raise NativePoseReadbackError("Saved animation references a different target skeleton.")
    model = asset.get_editor_property("data_model_interface")
    if model is None or _rate(model) != (
        baked["display_rate"]["numerator"], baked["display_rate"]["denominator"]
    ):
        raise NativePoseReadbackError("Saved animation native data-model frame rate differs.")
    if (library.get_num_frames(asset) != baked["sampled_frames"]
            or library.get_num_keys(asset) != baked["sampled_keys"]):
        raise NativePoseReadbackError("Saved native animation frame/key counts differ.")

    # Enumerate all native bone tracks, not merely the planned subset. An
    # unexpected track may drive the character and invalidate the conversion.
    names = [str(name) for name in model.get_bone_track_names()]
    expected_names = [row["bone_name"] for row in baked["bone_tracks"]]
    if (len(names) != len(set(names)) or set(names) != set(expected_names)):
        raise NativePoseReadbackError("Saved native bone tracks differ from approved mapping.")

    mismatches = []
    peak_position, peak_rotation, peak_scale = 0.0, 0.0, 0.0
    for row in baked["bone_tracks"]:
        name = row["bone_name"]
        raw = library.get_raw_track_data(asset, name)
        if not isinstance(raw, (list, tuple)) or len(raw) != 3:
            raise NativePoseReadbackError("Unreal did not return three raw key channels for " + name)
        for channel, expected, size, tol in (
            (raw[0], row["position_keys_cm"], 3, position_tolerance_cm),
            (raw[1], row["rotation_keys_xyzw"], 4, rotation_tolerance_degrees),
            (raw[2], row["scale_keys_xyz"], 3, scale_tolerance),
        ):
            if len(channel) != baked["sampled_keys"]:
                raise NativePoseReadbackError(
                    "Native bone channel has missing/contracted keys for " + name
                )
            for index, (native_value, planned) in enumerate(zip(channel, expected)):
                observed = _components(native_value, size, name)
                error = (_angle(observed, planned) if size == 4 else
                         max(abs(a - b) for a, b in zip(observed, planned)))
                if size == 4:
                    peak_rotation = max(peak_rotation, error)
                elif channel is raw[0]:
                    peak_position = max(peak_position, error)
                else:
                    peak_scale = max(peak_scale, error)
                if error > tol:
                    mismatches.append({"bone_name": name, "channel": (
                        "rotation" if size == 4 else
                        "position" if channel is raw[0] else "scale"),
                        "key_index": index, "error": round(error, 6)})
                    if len(mismatches) > 100:
                        raise NativePoseReadbackError("Excessive native bone readback differences.")

    status = ("NATIVE_SAVED_BONE_KEY_READBACK_PASS" if not mismatches
              else "NATIVE_SAVED_BONE_KEY_READBACK_FAIL")
    result = {
        "kind": "cutsceneai.studio.native_skeletal_pose_readback",
        "schema_version": "1", "status": status,
        "source_pose_bake_sha256": receipt["source_sha256"],
        "native_write_receipt_sha256": hashlib.sha256(
            Path(write_receipt_path).read_bytes()).hexdigest(),
        "target_project_identity_sha256": project_identity,
        "target_animation_asset_path": target["animation_asset_path"],
        "generation_editor_pid": writer_pid,
        "observation_editor_pid": os.getpid(),
        "reopened_in_distinct_editor_process": True,
        "native_bone_key_readback_verified": not mismatches,
        "full_cutscene_fidelity_verified": False,
        "bone_count": len(expected_names), "keys_per_bone": baked["sampled_keys"],
        "max_position_error_cm": round(peak_position, 6),
        "max_rotation_error_degrees": round(peak_rotation, 6),
        "max_scale_error": round(peak_scale, 8),
        "mismatches": mismatches,
        "further_required": [
            "Retargeted skeletal playback on the intended target mesh",
            "Source-vs-target pose and rendered silhouette comparison",
            "Independent calibrated rig, root/actor and Timeline acceptance",
        ],
    }
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return result
