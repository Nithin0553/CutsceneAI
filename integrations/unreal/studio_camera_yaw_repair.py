"""One static CineCamera yaw-only actor repair, native revalidation required.

No model/yaw arguments are accepted. Live CineCamera actor and component
rotation, position, scale, parentage, Sequencer owners and exact staged UObject
are checked immediately before one reversible world yaw mutation. Original
actor transform and component orientation are rechecked after rollback. Native
property save is NOT reopened CineTwin or rendered fidelity evidence.
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
for d in (ROOT / "packages/studio", ROOT / "integrations/unreal"):
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))

import readback_math
import studio_camera_position_repair as position_native
import studio_camera_yaw_evidence as evidence


class StaticCameraYawRepairError(ValueError):
    """The native editor cannot prove a safe static camera yaw owner."""


def _load(path: Path) -> dict:
    return evidence.readback._safe_json(path)[0]


def _wrap(a: float) -> float:
    return (a + 180) % 360 - 180


def _vec3(value: Any) -> tuple[float, float, float]:
    try:
        xyz = (float(value.x), float(value.y), float(value.z))
    except (AttributeError, TypeError, ValueError) as exc:
        raise StaticCameraYawRepairError("Native camera vector unobservable.") from exc
    if not all(math.isfinite(v) and abs(v) < 10_000_000 for v in xyz):
        raise StaticCameraYawRepairError("Native camera vector unbounded.")
    return xyz


def _rotator(actor: Any) -> tuple[float, float, float]:
    try:
        r = actor.get_actor_rotation()
        values = tuple(float(getattr(r, attr)) for attr in ("roll", "pitch", "yaw"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise StaticCameraYawRepairError("Native actor rotation unavailable.") from exc
    if any(not math.isfinite(v) or abs(v) > 360000 for v in values):
        raise StaticCameraYawRepairError("Native camera orientation unbounded.")
    return values


def _quat_native(q: Any) -> tuple[float, float, float, float]:
    try:
        values = tuple(float(getattr(q, a)) for a in ("x", "y", "z", "w"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise StaticCameraYawRepairError("Native camera component quaternion missing.") from exc
    if (not all(math.isfinite(v) for v in values)
            or abs(sum(v*v for v in values)-1) > 0.01):
        raise StaticCameraYawRepairError("Native camera component quaternion is not unit.")
    return values


def _component_world(component: Any) -> tuple[float, float, float, float]:
    getter = getattr(component, "get_world_transform", None)
    if not callable(getter):
        getter = getattr(component, "get_component_transform", None)
    if not callable(getter):
        raise StaticCameraYawRepairError("Native CineCameraComponent world basis is missing.")
    q = _quat_native(getter().rotation)
    # UE axial quaternion -> canonical reflected basis; this is the same
    # validated mapping as the native Cinetwin rig readback.
    return (-q[1], -q[2], q[0], q[3])


def _component_is_actor_owned(component: Any, actor: Any) -> None:
    try:
        relative = component.get_relative_transform()
        translation = _vec3(relative.translation)
        scale = _vec3(relative.scale3d)
        quat = _quat_native(relative.rotation)
        if (math.dist(translation, (0, 0, 0)) > 0.1
                or max(abs(v-1) for v in scale) > 0.01
                or evidence._qangle(quat, (0., 0., 0., 1.)) > 0.25):
            raise StaticCameraYawRepairError(
                "Native camera component has an independent relative transform."
            )
        actor_q = readback_math.unreal_rpy_to_canonical_quat(*_rotator(actor))
        if evidence._qangle(_component_world(component), actor_q) > 0.25:
            raise StaticCameraYawRepairError(
                "Native CineCameraComponent world orientation is not actor-owned."
            )
    except StaticCameraYawRepairError:
        raise
    except (AttributeError, TypeError, ValueError, RuntimeError,
            evidence.StaticCameraYawError) as exc:
        raise StaticCameraYawRepairError(
            "Native camera component/actor basis cannot be independently verified."
        ) from exc


def _same_rpy(actual: tuple[float, ...], expected: list[float],
              tolerance: float = 0.1) -> bool:
    return all(abs(_wrap(a-b)) <= tolerance for a,b in zip(actual, expected))


def attempt(api: Any, workspace: Path, job: dict, request: dict) -> dict:
    candidate = Path(job["candidate_dir"]).resolve()
    if request.get("strategy") != "restore_static_camera_actor_yaw":
        raise StaticCameraYawRepairError("Wrong static camera rotation strategy.")
    fid = str(request.get("feedback_id") or "")
    if not re.fullmatch(r"[a-f0-9]{32}", fid):
        raise StaticCameraYawRepairError(
            "Exact current user camera rotation feedback required."
        )
    active = _load(candidate / ("user-feedback-active-" + job["job_id"] + ".json"))
    comment = _load(candidate / ("user-feedback-" + fid + ".json"))
    if (active.get("job_id") != job["job_id"]
            or active.get("candidate_id") != job["candidate_id"]
            or active.get("feedback_id") != fid
            or comment.get("kind") != "cutsceneai.studio.user_feedback"
            or comment.get("feedback_id") != fid
            or comment.get("job_id") != job["job_id"]
            or comment.get("candidate_id") != job["candidate_id"]
            or not evidence.message_requests_yaw(comment.get("message"))):
        raise StaticCameraYawRepairError(
            "No current consent for the isolated static camera yaw repair."
        )
    proof = evidence.build(workspace, job)
    if (request.get("camera_yaw_repair_sha256")
            != proof["camera_yaw_repair_sha256"]
            or request.get("source_camera_occurrence_id")
            != proof["source_camera_occurrence_id"]):
        raise StaticCameraYawRepairError(
            "Source/native original camera yaw proof changed before execution."
        )
    setup_path = Path(str(job.get("setup_receipt_file") or ""))
    if (setup_path.is_symlink() or not setup_path.is_file()
            or setup_path.resolve().parent != candidate):
        raise StaticCameraYawRepairError(
            "Exact source-created camera actor receipt is missing."
        )
    rows = _load(setup_path).get("actors_created")
    if not isinstance(rows, list):
        raise StaticCameraYawRepairError("Native setup actor inventory absent.")
    staged = [row for row in rows
              if isinstance(row, dict) and row.get("kind") == "entity.camera"
              and row.get("name") == proof["source_camera_name"]
              and row.get("label") == proof["target_actor_label"]]
    if len(staged) != 1:
        raise StaticCameraYawRepairError(
            "Only the exact source-created native CineCamera may be rotated."
        )
    sequence = api.load_asset(job["sequence_path"])
    if sequence is None:
        raise StaticCameraYawRepairError(
            "Exact generated native Level Sequence is missing."
        )
    try:
        position_native._static_transform_ownership(api, sequence)
    except position_native.StaticCameraNativeRepairError as exc:
        raise StaticCameraYawRepairError(
            "Native Sequencer track/property ownership is not isolated."
        ) from exc
    scene = api.get_editor_subsystem(api.EditorActorSubsystem)
    actors = list(scene.get_all_level_actors())
    if len(actors) > 10000:
        raise StaticCameraYawRepairError("Native actor inventory is unbounded.")
    found = [a for a in actors
             if str(a.get_actor_label()) == proof["target_actor_label"]]
    if len(found) != 1:
        raise StaticCameraYawRepairError(
            "Native camera actor label is missing or duplicated."
        )
    actor = found[0]
    get_path = getattr(actor, "get_path_name", None)
    expected_path = staged[0].get("native_actor_path")
    if (not isinstance(expected_path, str)
            or not expected_path.startswith("/Game/")
            or len(expected_path) > 1024
            or not callable(get_path) or str(get_path()) != expected_path
            or str(actor.get_class().get_name()) != "CineCameraActor"):
        raise StaticCameraYawRepairError(
            "Live CineCamera UObject differs from original source-created actor."
        )
    if (actor.get_attach_parent_actor() is not None
            or any(other is not actor
                   and other.get_attach_parent_actor() is actor
                   for other in actors)):
        raise StaticCameraYawRepairError(
            "Parent/child camera attachments own part of the cinematic basis."
        )
    get_component = getattr(actor, "get_cine_camera_component", None)
    if not callable(get_component) or get_component() is None:
        raise StaticCameraYawRepairError(
            "Native CineCamera component is missing."
        )
    component = get_component()
    original_rpy = _rotator(actor)
    original_pos = _vec3(actor.get_actor_location())
    scales = _vec3(actor.get_actor_scale3d())
    if (max(abs(s-1) for s in scales) > 0.01
            or not _same_rpy(
                original_rpy, proof["native_rotation_rpy_before_degrees"],
            )
            or math.dist(original_pos, proof["native_position_before_cm"]) > 0.1):
        raise StaticCameraYawRepairError(
            "Live actor pose/scale differs from original reopened source capture."
        )
    _component_is_actor_owned(component, actor)
    new_rpy = proof["source_aligned_rotation_rpy_degrees"]
    if (not _same_rpy(new_rpy[:2], original_rpy[:2], 0.25)
            or abs(_wrap(new_rpy[2] - original_rpy[2])) < 2
            or abs(_wrap(new_rpy[2] - original_rpy[2])) > 90):
        raise StaticCameraYawRepairError(
            "Source-aligned actor update is not bounded to native world yaw."
        )
    modified = False
    saved = False
    try:
        modified = True  # Unreal notifications can mutate then raise.
        # Preserve CURRENT native roll/pitch exactly. Source pitch/roll
        # were separately checked within 0.25 degrees, but writing their
        # approximate source values would violate a yaw-only mutation.
        target_rpy = (original_rpy[0], original_rpy[1], new_rpy[2])
        result = actor.set_actor_rotation(
            api.Rotator(target_rpy[1], target_rpy[2], target_rpy[0]), True,
        )
        if result is not True:
            raise StaticCameraYawRepairError(
                "Native CineCamera yaw setter did not confirm its mutation."
            )
        actual_rpy = _rotator(actor)
        if (not _same_rpy(actual_rpy, target_rpy)
                or math.dist(_vec3(actor.get_actor_location()), original_pos) > 0.1
                or max(abs(s-1) for s in _vec3(actor.get_actor_scale3d())) > 0.01):
            raise StaticCameraYawRepairError(
                "Camera rotation edit unexpectedly changed transform properties."
            )
        _component_is_actor_owned(component, actor)
        import studio_auto_scene
        studio_auto_scene._save_level(api, job["expected_level"])
        saved = True
        return {
            "status": "CAMERA_STATIC_YAW_SAVED_REOPENED_CINETWIN_PENDING",
            "camera_yaw_repair_sha256": proof["camera_yaw_repair_sha256"],
            "source_camera_occurrence_id": proof["source_camera_occurrence_id"],
            "changes": 1,
            "native_actor_yaw_error_after_degrees": abs(
                _wrap(actual_rpy[2] - new_rpy[2]),
            ),
            "native_base_and_component_rotation_readback_verified": True,
            "persistence_after_editor_restart_verified": False,
            "cinetwin_reopened_time_grid_verified_after_repair": False,
            "rendered_camera_facing_verified": False,
            "full_cutscene_fidelity_verified": False,
        }
    finally:
        if modified and not saved:
            # Best effort compensating edit; an interrupted native disk SAVE
            # is never treated as confirmed persisted rollback.
            try:
                actor.set_actor_rotation(api.Rotator(
                    original_rpy[1], original_rpy[2], original_rpy[0],
                ), True)
                now = _vec3(actor.get_actor_location())
                if math.dist(now, original_pos) > 0.1:
                    actor.set_actor_location(api.Vector(*original_pos), False, True)
                if (not _same_rpy(_rotator(actor), original_rpy)
                        or math.dist(
                            _vec3(actor.get_actor_location()), original_pos
                        ) > 0.1):
                    raise StaticCameraYawRepairError(
                        "Original actor rotation and location rollback failed."
                    )
                _component_is_actor_owned(component, actor)
            except (AttributeError, TypeError, ValueError, RuntimeError) as exc:
                raise StaticCameraYawRepairError(
                    "Static camera yaw rollback unverified; inspect editor manually."
                ) from exc
