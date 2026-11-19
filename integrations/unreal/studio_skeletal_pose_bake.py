"""Isolated Unreal 5.8 skeletal pose-bake writer for an approved target rig.

This module is deliberately NOT registered as an always-on agent tool.
Only a source-authenticated, immutable reviewed pose bake can create one NEW
AnimSequence on the selected Unreal project. An error after asset creation
leaves a durable partial receipt and must never trigger automatic replay.
Actual Unreal API/runtime acceptance remains a separate editor gate.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path


class NativePoseBakeError(RuntimeError):
    pass


def _path(asset):
    return str(asset.get_path_name()).split(".", 1)[0] if asset is not None else ""


def _class(asset):
    return str(asset.get_class().get_name()) if asset is not None else ""


def _read_bake(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size < 256 * 1024 * 1024:
        raise NativePoseBakeError("Source pose-bake evidence is missing, symlinked or oversized.")
    artifact = json.loads(path.read_text(encoding="utf-8-sig"))
    if artifact.get("kind") != "cutsceneai.studio.skeletal_pose_bake" or artifact.get("schema_version") != "1":
        raise NativePoseBakeError("Expected a versioned, approved skeletal pose-bake artifact.")
    expected = artifact.get("canonical_payload_sha256")
    document = {key: value for key, value in artifact.items() if key != "canonical_payload_sha256"}
    observed = hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":"),
                                        allow_nan=False).encode("utf-8")).hexdigest()
    if expected != observed:
        raise NativePoseBakeError("Source pose-bake payload checksum mismatches immutable planning.")
    count = artifact.get("sampled_keys")
    bones = artifact.get("bone_tracks")
    if (type(count) is not int or not 2 <= count <= 4001
            or not isinstance(bones, list) or not 1 <= len(bones) <= 256
            or len(set(row.get("bone_name") for row in bones)) != len(bones)
            or artifact.get("sampled_frames") != count-1):
        raise NativePoseBakeError("Pose-bake frames or target bone list is invalid.")
    for bone in bones:
        if not isinstance(bone.get("bone_name"), str) or not bone["bone_name"]:
            raise NativePoseBakeError("Target bone has no identity.")
        ref = bone.get("approved_target_local_reference")
        if not isinstance(ref, dict) or set(ref) != {
            "position_cm", "rotation_xyzw", "scale_xyz"
        }:
            raise NativePoseBakeError("Native bone must carry its complete approved bind reference.")
        for name, length in (("position_cm", 3), ("rotation_xyzw", 4), ("scale_xyz", 3)):
            value = ref.get(name)
            if (not isinstance(value, (list, tuple)) or len(value) != length
                    or any(type(x) not in (int, float) or not math.isfinite(x) for x in value)):
                raise NativePoseBakeError("Approved target skeletal reference contains invalid values.")
            if length == 4 and abs(sum(v*v for v in value)-1) > 0.02:
                raise NativePoseBakeError("Approved target bone rest quaternion must be normalized.")
        for key, size in (
            ("position_keys_cm", 3), ("rotation_keys_xyzw", 4),
            ("scale_keys_xyz", 3),
        ):
            values = bone.get(key)
            if not isinstance(values, list) or len(values) != count:
                raise NativePoseBakeError("Incomplete native sampled bone key stream.")
            for sample in values:
                if (not isinstance(sample, (list, tuple)) or len(sample) != size
                        or not all(type(x) in (int, float) and math.isfinite(x)
                                   for x in sample)):
                    raise NativePoseBakeError("Invalid or nonfinite native skeletal key.")
                if size == 4 and abs(sum(v*v for v in sample)-1) > 0.02:
                    raise NativePoseBakeError("Non-unit native skeletal rotation key.")
    return artifact


def _write_receipt(path, receipt, *, replace=False):
    with Path(path).open("w" if replace else "x", encoding="utf-8") as output:
        json.dump(receipt, output, indent=2, allow_nan=False)
        output.write("\n")


def execute(
    pose_bake_path, receipt_path, *, api=None, explicit_native_approval=False,
) -> dict:
    """Create a new native asset; never overwrite/retry a possibly executed job."""
    if not explicit_native_approval:
        raise NativePoseBakeError("Skeletal asset creation needs explicit operator approval.")
    baked = _read_bake(pose_bake_path)
    target = baked["target"]
    import re
    package = re.compile(r"/Game(?:/[A-Za-z0-9_]+)+")
    skeleton_path, output_path = target["skeleton_asset_path"], target["animation_asset_path"]
    if (not package.fullmatch(skeleton_path) or not package.fullmatch(output_path)
            or output_path == skeleton_path):
        raise NativePoseBakeError("Approved Unreal asset path is unsafe.")
    output = Path(receipt_path)
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        raise NativePoseBakeError("Native bake receipt must have a new existing parent and filename.")
    if api is None:
        import unreal as api
    project = Path(api.Paths.get_project_file_path()).resolve()
    if not project.is_file() or project.is_symlink():
        raise NativePoseBakeError("Unreal project path is missing or unsafe.")
    project_identity = hashlib.sha256(
        str(project).encode("utf-8") + b"\0" + project.read_bytes()
    ).hexdigest()
    if project_identity != target.get("unreal_project_identity_sha256"):
        raise NativePoseBakeError("Selected Unreal project differs from approved target skeletal bake.")
    if not str(api.SystemLibrary.get_engine_version()).startswith("5.8."):
        raise NativePoseBakeError("Native skeletal pose-bake needs Unreal 5.8 API acceptance.")
    skeleton = api.load_asset(skeleton_path)
    if _class(skeleton) != "Skeleton" or _path(skeleton) != skeleton_path:
        raise NativePoseBakeError("Approved target skeleton asset is missing or has the wrong native class.")
    # The compiler's reviewed target rest pose is NOT sufficient evidence:
    # compare it with the actual current Unreal Skeleton *before* touching
    # any asset. A changed bone, bind transform or unavailable native pose
    # API blocks the transfer rather than baking onto a different skeleton.
    native_pose_api = getattr(api, "AnimPoseExtensions", None)
    if not all(callable(getattr(native_pose_api, name, None)) for name in (
            "get_reference_pose", "get_bone_names", "get_bone_pose")):
        raise NativePoseBakeError("Unreal native reference-pose API unavailable.")
    try:
        pose = native_pose_api.get_reference_pose(skeleton)
        observed_bones = {str(name) for name in native_pose_api.get_bone_names(pose)}
        planned_bones = {row["bone_name"] for row in baked["bone_tracks"]}
        if not planned_bones.issubset(observed_bones):
            raise NativePoseBakeError("Approved target bone mapping is not in current native skeleton.")
        for row in baked["bone_tracks"]:
            ref = row["approved_target_local_reference"]
            native = native_pose_api.get_bone_pose(pose, row["bone_name"])
            for key, observed, expected, tol in (
                ("position", native.translation, ref["position_cm"], 0.02),
                ("scale", native.scale3d, ref["scale_xyz"], 0.0001),
            ):
                values = (float(observed.x), float(observed.y), float(observed.z))
                if any(abs(a - float(b)) > tol for a, b in zip(values, expected)):
                    raise NativePoseBakeError(
                        "Native target skeleton " + key
                        + " bind pose changed for bone " + row["bone_name"]
                    )
            q = native.rotation
            current = (float(q.x), float(q.y), float(q.z), float(q.w))
            ref_q = ref["rotation_xyzw"]
            dot = abs(sum(a * float(b) for a, b in zip(current, ref_q)))
            if not math.isfinite(dot) or dot < 0.999999:
                raise NativePoseBakeError(
                    "Native target skeleton orientation bind pose changed for bone "
                    + row["bone_name"]
                )
    except (AttributeError, RuntimeError, TypeError, ValueError) as error:
        if isinstance(error, NativePoseBakeError):
            raise
        raise NativePoseBakeError(
            "Could not independently verify native skeleton rest pose before baking."
        ) from error
    library = api.EditorAssetLibrary
    if library.does_asset_exist(output_path):
        raise NativePoseBakeError("Refusing to overwrite or reuse a target AnimSequence.")
    for obj, name in (
        (api, "AnimSequenceFactory"), (api, "AnimSequence"), (api, "FrameRate"),
        (api, "FrameNumber"), (api, "Vector"), (api, "Quat"),
        (api.AssetToolsHelpers, "get_asset_tools"),
        (library, "save_loaded_asset"),
    ):
        if not hasattr(obj, name):
            raise NativePoseBakeError("Unreal native pose-bake API unavailable: " + name)
    receipt = {
        "kind": "cutsceneai.studio.native_skeletal_pose_bake_receipt",
        "schema_version": "1", "source_sha256": hashlib.sha256(Path(pose_bake_path).read_bytes()).hexdigest(),
        "source_entity_id": baked["source_entity_id"], "target_project_identity_sha256": project_identity,
        "target_skeleton_asset_path": skeleton_path, "target_animation_asset_path": output_path,
        "status": "PREFLIGHT_PASSED_NOT_GENERATED", "native_asset_writes_possible": False,
        "fidelity_verified": False, "native_target_readback_verified": False,
    }
    _write_receipt(output, receipt)
    native_started = False
    try:
        factory = api.AnimSequenceFactory()
        factory.set_editor_property("target_skeleton", skeleton)
        tools = api.AssetToolsHelpers.get_asset_tools()
        folder, filename = output_path.rsplit("/", 1)
        native_started = True
        receipt["native_asset_writes_possible"] = True
        receipt["status"] = "NATIVE_WRITE_STARTED"
        _write_receipt(output, receipt, replace=True)
        asset = tools.create_asset(filename, folder, api.AnimSequence, factory)
        if _class(asset) != "AnimSequence" or _path(asset) != output_path:
            raise NativePoseBakeError("Unreal native factory did not create the approved AnimSequence.")
        assigned = asset.get_editor_property("skeleton")
        if _path(assigned) != skeleton_path:
            raise NativePoseBakeError("Created animation is not assigned to the approved target skeleton.")
        get_controller = getattr(asset, "get_controller", None)
        controller = get_controller() if callable(get_controller) else asset.get_editor_property("controller")
        for name in ("set_frame_rate", "set_number_of_frames",
                     "add_bone_track", "set_bone_track_keys"):
            if not callable(getattr(controller, name, None)):
                raise NativePoseBakeError("Target AnimSequence is missing required AnimationDataController." )
        rate = baked["display_rate"]
        controller.set_frame_rate(api.FrameRate(rate["numerator"], rate["denominator"]), False)
        controller.set_number_of_frames(api.FrameNumber(baked["sampled_frames"]), False)
        for row in baked["bone_tracks"]:
            bone = row["bone_name"]
            added = controller.add_bone_track(bone, False)
            if added is False or (type(added) is int and added < 0):
                raise NativePoseBakeError("Unreal rejected new skeletal track " + bone)
            positions = [api.Vector(*v) for v in row["position_keys_cm"]]
            rotations = [api.Quat(*v) for v in row["rotation_keys_xyzw"]]
            scales = [api.Vector(*v) for v in row["scale_keys_xyz"]]
            if controller.set_bone_track_keys(
                    bone, positions, rotations, scales, False) is False:
                raise NativePoseBakeError("Unreal did not write expected bone keys for " + bone)
        if not library.save_loaded_asset(asset):
            raise NativePoseBakeError("Native skeletal pose-bake asset could not be saved.")
        receipt["status"] = "NATIVE_SAVED_PENDING_INDEPENDENT_READBACK"
        receipt["native_target_readback_verified"] = False
        receipt["saved_bone_count"] = len(baked["bone_tracks"])
        receipt["saved_key_count_per_bone"] = baked["sampled_keys"]
    except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
        receipt["status"] = ("PARTIAL_NATIVE_WRITE_NO_AUTORETRY" if native_started
                              else "FAILED_BEFORE_NATIVE_MUTATION")
        receipt["error"] = type(exc).__name__ + ": " + str(exc)[:500]
        _write_receipt(output, receipt, replace=True)
        raise NativePoseBakeError(
            "Native skeletal bake failed; preserve partial candidate and DO NOT replay. "
            + str(exc)
        ) from exc
    _write_receipt(output, receipt, replace=True)
    return receipt
