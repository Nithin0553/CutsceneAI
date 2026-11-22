"""One explicitly requested, source-derived static character yaw-only repair.

This is a narrow native adapter, not general character orientation/retargeting.
It NEVER touches SkeletalMeshComponent, skeleton, root bones, AnimSequence,
Sequencer tracks or imported asset data. All source/target numbers come from a
recomputed approved full-grid reopened CineTwin report, not model output.

A registered agent dispatch gives at most one editor-thread attempt with a
durable write-ahead claim. Setter failures roll back to the original rotator.
The successful save is not a separately reopened CineTwin or rendered proof.
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT / "packages/studio", ROOT / "integrations/unreal"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import studio_character_facing_ownership as owner
import studio_static_character_yaw_evidence as evidence


class StaticCharacterYawRepairError(ValueError):
    """Requested native actor yaw would not be a safe bounded change."""


def _load(path: Path) -> dict:
    return evidence.readback._safe_json(path)[0]


def _rotator(rotation: Any) -> tuple[float, float, float]:
    try:
        point = tuple(float(getattr(rotation, key))
                      for key in ("roll", "pitch", "yaw"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise StaticCharacterYawRepairError(
            "Cannot read current native actor world rotation."
        ) from exc
    if not all(math.isfinite(v) and abs(v) <= 360000 for v in point):
        raise StaticCharacterYawRepairError("Native actor orientation is unbounded.")
    return point


def _wrap(value: float) -> float:
    return (value + 180.0) % 360.0 - 180.0


def _no_active_native_skeletal_animation(component: Any, mesh: Any) -> None:
    """Reject even latent AnimBP/postprocess/root animation with no Sequencer keys.

    The animation mode alone is never accepted as proof of a still skeleton.
    Require the editor to expose the exact inactive animation state; any
    missing API or non-None animation/instance must stop before mutation.
    """
    try:
        mode = str(component.get_animation_mode())
        if mode not in {
            "AnimationMode.ANIMATION_CUSTOM_MODE",
            "ANIMATION_CUSTOM_MODE",
        }:
            raise StaticCharacterYawRepairError(
                "Native skeletal animation mode may own character facing."
            )
        if (component.get_anim_instance() is not None
                or component.get_post_process_instance() is not None):
            raise StaticCharacterYawRepairError(
                "Active animation blueprint or postprocess controls the skeleton."
            )
        if component.get_editor_property("anim_class") is not None:
            raise StaticCharacterYawRepairError(
                "An animation blueprint class is attached to the native component."
            )
        animation_data = component.get_editor_property("animation_data")
        if (animation_data is None
                or getattr(animation_data, "anim_to_play", "UNKNOWN") is not None):
            raise StaticCharacterYawRepairError(
                "Native animation single-node asset is active or unobservable."
            )
        # A mesh-authored postprocess AnimBP can run when no visible
        # Sequencer animation track or component AnimInstance exists.
        if mesh.get_editor_property("post_process_anim_blueprint") is not None:
            raise StaticCharacterYawRepairError(
                "Skeletal mesh has a postprocess animation blueprint."
            )
    except StaticCharacterYawRepairError:
        raise
    except (AttributeError, TypeError, ValueError, RuntimeError) as exc:
        raise StaticCharacterYawRepairError(
            "Unreal cannot independently prove inactive skeletal animation."
        ) from exc


def attempt(api: Any, workspace: Path, job: dict, request: dict) -> dict:
    candidate = Path(job["candidate_dir"]).resolve()
    if request.get("strategy") != "restore_static_character_actor_yaw":
        raise StaticCharacterYawRepairError("Wrong static character facing repair.")
    feedback_id = str(request.get("feedback_id") or "")
    if re.fullmatch(r"[a-f0-9]{32}", feedback_id) is None:
        raise StaticCharacterYawRepairError(
            "Current exact character-facing feedback is required."
        )
    active = _load(candidate / ("user-feedback-active-" + job["job_id"] + ".json"))
    feedback = _load(candidate / ("user-feedback-" + feedback_id + ".json"))
    if (active.get("feedback_id") != feedback_id
            or active.get("job_id") != job["job_id"]
            or active.get("candidate_id") != job["candidate_id"]
            or feedback.get("kind") != "cutsceneai.studio.user_feedback"
            or feedback.get("feedback_id") != feedback_id
            or feedback.get("job_id") != job["job_id"]
            or feedback.get("candidate_id") != job["candidate_id"]
            or not evidence.message_requests_static_yaw(feedback.get("message"))):
        raise StaticCharacterYawRepairError(
            "No current explicit source-scoped character facing consent."
        )
    proof = evidence.build(workspace, job)
    if (request.get("character_yaw_repair_sha256")
            != proof["character_yaw_repair_sha256"]
            or request.get("source_entity_id") != proof["source_entity_id"]):
        raise StaticCharacterYawRepairError(
            "Source-bound full-frame static character yaw proof changed."
        )
    setup_path = Path(str(job.get("setup_receipt_file") or ""))
    if (setup_path.is_symlink() or not setup_path.is_file()
            or setup_path.resolve().parent != candidate):
        raise StaticCharacterYawRepairError(
            "Exact generated character actor setup receipt is missing."
        )
    created = [row for row in _load(setup_path).get("actors_created", [])
               if isinstance(row, dict)
               and row.get("kind") == "entity.character"
               and row.get("name") == proof["source_character_name"]
               and row.get("label") == proof["target_actor_label"]]
    if len(created) != 1:
        raise StaticCharacterYawRepairError(
            "Only one newly staged source character may be rotated."
        )
    sequence = api.load_asset(job["sequence_path"])
    if sequence is None:
        raise StaticCharacterYawRepairError("Generated source-bound sequence missing.")
    scene = api.get_editor_subsystem(api.EditorActorSubsystem)
    actors = list(scene.get_all_level_actors())
    matches = [a for a in actors
               if str(a.get_actor_label()) == proof["target_actor_label"]]
    if len(matches) != 1:
        raise StaticCharacterYawRepairError(
            "Native character label is no longer unique."
        )
    actor = matches[0]
    observed = owner.inspect(
        api, sequence, actor,
        expected_actor_label=proof["target_actor_label"],
        expected_mesh_asset_path=proof["target_mesh_asset_path"],
        all_level_actors=actors,
    )
    if (observed["status"]
            != "STATIC_NATIVE_OWNER_CANDIDATE_REQUIRES_SOURCE_PROOF"
            or observed["blocking_reasons"]):
        raise StaticCharacterYawRepairError(
            "Current native actor/component/Sequencer owner is not isolated."
        )
    component, = actor.get_components_by_class(api.SkeletalMeshComponent)
    mesh = component.get_skeletal_mesh_asset()
    _no_active_native_skeletal_animation(component, mesh)
    original = _rotator(actor.get_actor_rotation())
    if (max(abs(v) for v in original[:2]) > 0.25
            or abs(_wrap(original[2] - proof["native_yaw_before_degrees"])) > 0.1):
        raise StaticCharacterYawRepairError(
            "Fresh native character actor yaw differs from reopened source evidence."
        )
    initial_loc = actor.get_actor_location()
    original_xyz = (float(initial_loc.x), float(initial_loc.y), float(initial_loc.z))
    if not all(math.isfinite(v) and abs(v) < 1_000_000 for v in original_xyz):
        raise StaticCharacterYawRepairError("Native actor position is not finite.")
    target_yaw = proof["native_yaw_after_degrees"]
    # Verify native mesh world basis is currently actor-owned. A verified
    # identity relative component from inspect() is necessary, not sufficient.
    def _world_component_quat() -> tuple[float, float, float, float]:
        getter = getattr(component, "get_world_transform", None)
        if not callable(getter):
            getter = getattr(component, "get_component_transform", None)
        if not callable(getter):
            raise StaticCharacterYawRepairError(
                "Skeletal component world orientation readback unavailable."
            )
        q = getter().rotation
        values = tuple(float(getattr(q, axis)) for axis in ("x", "y", "z", "w"))
        if (not all(math.isfinite(v) for v in values)
                or abs(sum(v*v for v in values) - 1) > 0.02):
            raise StaticCharacterYawRepairError(
                "Native mesh component world orientation is invalid."
            )
        return values

    def _yaw_quat(value: float) -> tuple[float, float, float, float]:
        radians = math.radians(value) / 2
        return (0., 0., math.sin(radians), math.cos(radians))

    from rig_pose_calibration import _angle
    if _angle(_world_component_quat(), _yaw_quat(original[2])) > 0.25:
        raise StaticCharacterYawRepairError(
            "Live mesh component rotation differs from the actor base yaw."
        )
    changed = False
    saved = False
    try:
        # Write-ahead replay claim is created by studio_agent_executor.service_one
        # BEFORE this function is entered. Set rollback intent before calling
        # the native API; callbacks may mutate the actor and then throw.
        changed = True
        status = actor.set_actor_rotation(api.Rotator(0, target_yaw, 0), True)
        if status is not True:
            raise StaticCharacterYawRepairError(
                "Unreal refused the bounded character actor rotation."
            )
        after = _rotator(actor.get_actor_rotation())
        if (max(abs(v) for v in after[:2]) > 0.25
                or abs(_wrap(after[2] - target_yaw)) > 0.1
                or _angle(_world_component_quat(), _yaw_quat(target_yaw)) > 0.25):
            raise StaticCharacterYawRepairError(
                "Native actor/mesh base did not reach source-aligned yaw."
            )
        new_loc = actor.get_actor_location()
        if math.dist(original_xyz, (
                float(new_loc.x), float(new_loc.y), float(new_loc.z))) > 0.1:
            raise StaticCharacterYawRepairError(
                "Unexpected actor translation from yaw-only edit."
            )
        import studio_auto_scene
        studio_auto_scene._save_level(api, job["expected_level"])
        saved = True
        return {
            "status": "STATIC_CHARACTER_YAW_SAVED_REOPENED_CINETWIN_PENDING",
            "source_entity_id": proof["source_entity_id"],
            "character_yaw_repair_sha256": proof["character_yaw_repair_sha256"],
            "changes": 1, "native_base_yaw_after_degrees": round(after[2], 6),
            "native_actor_base_readback_verified": True,
            "native_mesh_world_basis_readback_verified": True,
            "skeletal_root_post_edit_sample_grid_verified": False,
            "persistence_after_editor_restart_verified": False,
            "cinetwin_reopened_time_grid_verified_after_repair": False,
            "rendered_character_facing_verified": False,
            "full_cutscene_fidelity_verified": False,
        }
    finally:
        if changed and not saved:
            actor.set_actor_rotation(api.Rotator(
                original[1], original[2], original[0],
            ), True)
