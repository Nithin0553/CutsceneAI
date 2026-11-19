"""Source-authenticated, reference-calibrated skeletal pose-bake contract.

Bakes evaluated Unity CineTwin local bone poses (including Timeline clip
blending and Unity .anim input) into a deterministic per-bone UE key stream.
This is not a native import: a separately approved target skeleton, rest
reference for *each* bone and measured native readback are still mandatory.

No implicit parent/bone map, axis, root-motion or scale correction is allowed.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

import sampling_plan
from rig_pose_calibration import _inverse, _mul, _quat, unreal_to_canonical_quat


class PoseBakeError(ValueError):
    pass


def _vector(values: Any, size: int, label: str):
    if not isinstance(values, (list, tuple)) or len(values) != size:
        raise PoseBakeError(f"{label} requires {size} values.")
    try:
        result = tuple(float(x) for x in values)
    except (TypeError, ValueError) as exc:
        raise PoseBakeError(f"Non-numeric {label}.") from exc
    if not all(math.isfinite(x) for x in result):
        raise PoseBakeError(f"Nonfinite {label}.")
    return result


def _rotate(q, v):
    x, y, z, w = q
    a, b, c = v
    tx, ty, tz = (2*(y*c-z*b), 2*(z*a-x*c), 2*(x*b-y*a))
    return (a+w*tx+y*tz-z*ty,
            b+w*ty+z*tx-x*tz,
            c+w*tz+x*ty-y*tx)


def _to_unreal_quat(q):
    x, y, z, w = _quat(q, "Calibrated canonical target quaternion")
    # Inverse axial basis (-unreal_y,-unreal_z,unreal_x) -> canonical XYZ.
    return (z, -x, -y, w)


def _to_unreal_delta_cm(v):
    x, y, z = v
    return (-100*z, 100*x, 100*y)


def _snapshot(csir: dict, capture: dict, csir_sha256: str):
    if not isinstance(csir_sha256, str) or len(csir_sha256) != 64:
        raise PoseBakeError("Skeletal bake requires the exact CSIR file SHA256.")
    if (capture.get("source", {}).get("csir_sha256") != csir_sha256
            or capture.get("cutscene_id") != csir.get("cutscene_id")):
        raise PoseBakeError("Skeletal capture identity differs from the immutable CSIR.")
    plan = sampling_plan.build_plan(csir, csir_sha256=csir_sha256)
    validation = sampling_plan.validate_capture(plan, capture)
    if validation["failures"]:
        raise PoseBakeError("Source skeletal capture fails validation: " + "; ".join(validation["failures"][:3]))
    return plan


def compile_baked_pose(
    csir: dict, capture: dict, approved: dict, *,
    csir_sha256: str, capture_sha256: str,
    max_frames: int = 4000, max_bones: int = 256,
) -> dict[str, Any]:
    """Compile the exact evaluated source frame grid into native-bound data.

    `approved` must be human-reviewed and pinned to the source CSIR and
    selected Unreal skeleton. Reference transforms are native rest/bind poses,
    NEVER first animated frame measurements.
    """
    plan = _snapshot(csir, capture, csir_sha256)
    if (not isinstance(capture_sha256, str) or len(capture_sha256) != 64
            or approved.get("kind") != "cutsceneai.studio.approved_skeletal_pose_bake"
            or approved.get("schema_version") != "1"
            or approved.get("reviewed_rest_and_bone_axes") is not True):
        raise PoseBakeError("Approved skeletal pose-bake reference and file hashes required.")
    src_id = {
        "csir_sha256": csir_sha256,
        "project_fingerprint": csir.get("source", {}).get("project_fingerprint"),
        "sequence_ref": csir.get("source", {}).get("sequence_ref"),
    }
    if (not all(src_id.values()) or approved.get("source_identity") != src_id
            or approved.get("source_capture_sha256") != capture_sha256):
        raise PoseBakeError("Skeletal pose-bake profile is stale for source/capture.")
    rig_id = approved.get("source_entity_id")
    if rig_id not in plan.get("skeletal_entity_ids", []):
        raise PoseBakeError("Source skeletal rig was not in the independently captured source plan.")
    rigs = [r for r in capture.get("rigs", []) if r.get("entity_id") == rig_id]
    if len(rigs) != 1:
        raise PoseBakeError("Missing or ambiguous source character rig.")
    bones = rigs[0].get("bones", [])
    identifiers = [bone.get("bone_id") for bone in bones]
    if (not identifiers or len(identifiers) > max_bones
            or len(set(identifiers)) != len(identifiers)):
        raise PoseBakeError("Source rig exceeds supported bone budget or contains duplicate identities.")
    bone_map = approved.get("bone_map")
    reference = approved.get("reference")
    if (not isinstance(bone_map, dict) or set(bone_map) != set(identifiers)
            or not isinstance(reference, dict) or set(reference) != set(identifiers)
            or len(set(bone_map.values())) != len(bone_map)):
        raise PoseBakeError("Every source rig bone needs one unique approved target and reference.")
    target = approved.get("target", {})
    skeleton_path = target.get("skeleton_asset_path")
    asset_path = target.get("animation_asset_path")
    if (not isinstance(skeleton_path, str) or not skeleton_path.startswith("/Game/")
            or not isinstance(asset_path, str) or not asset_path.startswith("/Game/")
            or skeleton_path == asset_path or ".." in skeleton_path or ".." in asset_path):
        raise PoseBakeError("Skeletal bake target must have isolated Unreal skeleton/animation asset paths.")

    rate = csir["timing"].get("display_rate") or csir["timing"]["source_rate"]
    numerator, denominator = int(rate["numerator"]), int(rate["denominator"])
    if numerator <= 0 or denominator <= 0:
        raise PoseBakeError("Invalid source display frame rate.")
    start = float(plan["samples"][0]["time_seconds"])
    end = float(plan["samples"][-1]["time_seconds"])
    frame_count = round((end-start)*numerator/denominator)
    if (frame_count <= 0 or frame_count >= max_frames
            or frame_count + 1 > len(plan["samples"])):
        raise PoseBakeError("Source skeletal bake exceeds frame budget or has invalid duration.")
    captured = {}
    for sample in capture["samples"]:
        t = round(float(sample["time_seconds"]), 8)
        if t in captured:
            raise PoseBakeError("Repeated source pose timestamp is ambiguous.")
        captured[t] = sample

    samples = []
    for frame in range(frame_count+1):
        timestamp = start + frame * denominator / numerator
        record = captured.get(round(timestamp, 8))
        if record is None:
            raise PoseBakeError("Missing exact source skeletal display frame for pose baking.")
        matching = [pose for pose in record.get("skeletal_poses", []) if pose.get("entity_id") == rig_id]
        if len(matching) != 1:
            raise PoseBakeError("Skeletal sample has missing or ambiguous rig.")
        present = matching[0]["bones"]
        if len(present) != len(bones) or set(x.get("bone_id") for x in present) != set(identifiers):
            raise PoseBakeError("Skeletal frame bone identities changed.")
        samples.append({x["bone_id"]: x["local_transform"] for x in present})

    outputs = []
    for source_bone_id in sorted(identifiers):
        conf = reference[source_bone_id]
        if not isinstance(conf, dict) or set(conf) != {
                "source_local_reference", "target_local_reference_unreal",
                "axis_alignment_canonical_xyzw", "translation_scale"}:
            raise PoseBakeError("Every approved bone requires source/target rest pose and axis calibration.")
        sr, tr = conf["source_local_reference"], conf["target_local_reference_unreal"]
        src_ref_p = _vector(sr.get("position_m"), 3, "Unity reference position")
        src_ref_q = _quat(sr.get("rotation_xyzw"), "Unity reference orientation")
        src_ref_s = _vector(sr.get("scale_xyz"), 3, "Unity reference scale")
        target_p = _vector(tr.get("position_cm"), 3, "Unreal reference position")
        target_q = unreal_to_canonical_quat(tr.get("rotation_xyzw"))
        target_s = _vector(tr.get("scale_xyz"), 3, "Unreal reference scale")
        axis = _quat(conf["axis_alignment_canonical_xyzw"], "Approved local axis alignment")
        factor = conf["translation_scale"]
        if (type(factor) not in (int, float) or not math.isfinite(factor)
                or not 0 < factor <= 100 or any(abs(v) < 1e-8 for v in target_s)):
            raise PoseBakeError("Invalid approved per-bone translation scale.")
        native = {"bone_name": bone_map[source_bone_id], "source_bone_id": source_bone_id,
                  "position_keys_cm": [], "rotation_keys_xyzw": [],
                  "scale_keys_xyz": []}
        for frame in samples:
            pose = frame[source_bone_id]
            actual_p = _vector(pose.get("position_m"), 3, "Source bone local position")
            actual_q = _quat(pose.get("rotation_xyzw"), "Source bone local orientation")
            actual_s = _vector(pose.get("scale_xyz"), 3, "Source bone local scale")
            if any(abs(actual_s[i]-src_ref_s[i]) > 1e-4 for i in range(3)):
                raise PoseBakeError("Animated bone scale/shear requires a separate native adapter.")
            source_delta_q = _mul(_inverse(src_ref_q), actual_q)
            mapped_delta_q = _mul(_mul(axis, source_delta_q), _inverse(axis))
            target_local_q = _mul(target_q, mapped_delta_q)
            source_delta = tuple(actual_p[i]-src_ref_p[i] for i in range(3))
            native_delta = _to_unreal_delta_cm(_rotate(axis, source_delta))
            native["position_keys_cm"].append([
                target_p[i] + factor*native_delta[i] for i in range(3)
            ])
            native["rotation_keys_xyzw"].append(list(_to_unreal_quat(target_local_q)))
            native["scale_keys_xyz"].append(list(target_s))
        outputs.append(native)
    artifact = {
        "kind": "cutsceneai.studio.skeletal_pose_bake",
        "schema_version": "1",
        "source_identity": src_id,
        "source_capture_sha256": capture_sha256,
        "source_entity_id": rig_id,
        "target": target,
        "sampled_frames": frame_count,
        "sampled_keys": frame_count + 1,
        "source_start_seconds": start,
        "display_rate": {"numerator": numerator, "denominator": denominator},
        "bone_tracks": outputs,
        "native_asset_generation_status": "NOT_EXECUTED",
        "native_skeleton_or_playback_fidelity_verified": False,
        "motion_owner": "SOURCE_EVALUATED_SKELETAL_LOCAL_POSES",
    }
    data = json.dumps(artifact, sort_keys=True, separators=(",", ":"), allow_nan=False)
    artifact["canonical_payload_sha256"] = hashlib.sha256(data.encode("utf-8")).hexdigest()
    return artifact
