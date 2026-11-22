"""Fail-closed, READ-ONLY Unreal ownership inspection for character facing.

Do not confuse the actor's world quaternion with SkeletalMeshComponent local
basis, imported FBX mesh, Sequencer keys, animation blueprints, retargeter,
physics, parent attachments, or root motion. This inspection is not a
registered repair adapter and NEVER authorizes a native rotation write.
Native behavior must still be verified in a real editor after software freeze.
"""
from __future__ import annotations

import math
from typing import Any

MAX_TRACKS = 10000
MAX_ACTORS = 10000
ALLOWED_READONLY_TRACKS = frozenset({
    "MovieSceneCameraCutTrack",
    "MovieSceneAudioTrack",
    "MovieSceneVisibilityTrack",
})


class CharacterFacingOwnershipError(ValueError):
    """A native rotation owner cannot be isolated from read-only evidence."""


def _vec3(value: Any, field: str) -> tuple[float, float, float]:
    try:
        values = tuple(float(getattr(value, axis)) for axis in ("x", "y", "z"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise CharacterFacingOwnershipError(
            f"Native {field} is missing or has invalid axes."
        ) from exc
    if not all(math.isfinite(v) and abs(v) < 1_000_000 for v in values):
        raise CharacterFacingOwnershipError(f"Native {field} is not finite.")
    return values


def _rotator(value: Any) -> tuple[float, float, float]:
    try:
        values = tuple(float(getattr(value, axis))
                       for axis in ("roll", "pitch", "yaw"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise CharacterFacingOwnershipError(
            "Native actor rotation channels cannot be observed."
        ) from exc
    if not all(math.isfinite(v) and abs(v) <= 360000 for v in values):
        raise CharacterFacingOwnershipError("Native actor rotator is invalid.")
    return values


def _track_kinds(api: Any, sequence: Any) -> list[str]:
    ext = getattr(api, "MovieSceneSequenceExtensions", None)
    if (sequence is None
            or not callable(getattr(ext, "get_bindings", None))
            or not callable(getattr(ext, "get_tracks", None))):
        raise CharacterFacingOwnershipError(
            "Complete native Sequencer master and bound track APIs are unavailable."
        )
    try:
        bindings = list(ext.get_bindings(sequence))
        master = list(ext.get_tracks(sequence))
        if len(bindings) > MAX_TRACKS or len(master) > MAX_TRACKS:
            raise CharacterFacingOwnershipError("Sequencer track/binding budget exceeded.")
        for binding in bindings:
            tracks = list(binding.get_tracks())
            if len(tracks) > MAX_TRACKS:
                raise CharacterFacingOwnershipError("Native bound track list is unbounded.")
            master.extend(tracks)
        if len(master) > MAX_TRACKS:
            raise CharacterFacingOwnershipError("Native Sequencer inventory exceeds budget.")
        kinds = [str(track.get_class().get_name()) for track in master]
        if any(not name or len(name) > 128 for name in kinds):
            raise CharacterFacingOwnershipError("Unknown native Sequencer track type.")
        return kinds
    except CharacterFacingOwnershipError:
        raise
    except (AttributeError, TypeError, ValueError, RuntimeError) as exc:
        raise CharacterFacingOwnershipError(
            "Native Sequencer binding/track inspection failed."
        ) from exc


def inspect(api: Any, sequence: Any, actor: Any, *,
            expected_actor_label: str, expected_mesh_asset_path: str,
            all_level_actors: list[Any]) -> dict[str, Any]:
    """Inventory *potential* owners, not proof of a safe actor rotation write.

    Return an actionable report even when native access is missing. A future
    registered edit must independently recheck exact source+target identity,
    a full CineTwin time grid, source/rig references, current user consent,
    rollback and post-edit native readback. This reporter does none of that.
    """
    result: dict[str, Any] = {
        "kind": "cutsceneai.studio.native_character_facing_owner_inspection",
        "schema_version": "1",
        "status": "BLOCKED_UNVERIFIED_OWNER",
        "owner_hypothesis": "UNKNOWN_NOT_PROVEN",
        "read_only": True,
        "native_edit_authorized": False,
        "actor_yaw_repair_authorized": False,
        "source_to_target_facing_verified": False,
        "full_cutscene_fidelity_verified": False,
        "blocking_reasons": [],
        "native_track_types": [],
    }
    reasons = result["blocking_reasons"]
    try:
        if (not isinstance(expected_actor_label, str) or not expected_actor_label
                or len(expected_actor_label) > 256
                or not isinstance(expected_mesh_asset_path, str)
                or not expected_mesh_asset_path.startswith("/Game/")
                or ".." in expected_mesh_asset_path
                or not isinstance(all_level_actors, list)
                or len(all_level_actors) > MAX_ACTORS):
            raise CharacterFacingOwnershipError(
                "Character identity, expected mesh or actor inventory is untrusted."
            )
        matches = [other for other in all_level_actors
                   if str(other.get_actor_label()) == expected_actor_label]
        if len(matches) != 1 or matches[0] is not actor:
            raise CharacterFacingOwnershipError(
                "Target actor is not the one unique mapped character."
            )
        result["target_actor_label"] = expected_actor_label
        native_class = str(actor.get_class().get_name())
        result["native_actor_class"] = native_class
        if native_class != "SkeletalMeshActor":
            reasons.append("UNSUPPORTED_CHARACTER_ACTOR_CLASS")
        parent = actor.get_attach_parent_actor()
        if parent is not None:
            reasons.append("ACTOR_PARENT_ATTACHMENT_OWNS_ORIENTATION")
        if any(other is not actor and other.get_attach_parent_actor() is actor
               for other in all_level_actors):
            reasons.append("ATTACHED_CHILDREN_CAN_BE_ROTATED")
        scale = _vec3(actor.get_actor_scale3d(), "actor scale")
        rpy = _rotator(actor.get_actor_rotation())
        result["native_actor_roll_pitch_yaw_degrees"] = list(rpy)
        if any(abs(axis) > 0.25 for axis in rpy[:2]):
            reasons.append("ACTOR_NON_UPRIGHT_ROLL_OR_PITCH")
        if max(abs(axis - 1) for axis in scale) > 0.01:
            reasons.append("NON_UNIT_ACTOR_SCALE")
        components = list(actor.get_components_by_class(api.SkeletalMeshComponent))
        if len(components) != 1:
            reasons.append("MISSING_OR_MULTIPLE_SKELETAL_MESH_COMPONENTS")
        else:
            component = components[0]
            mesh = component.get_skeletal_mesh_asset()
            asset = (str(mesh.get_path_name()).split(".", 1)[0]
                     if mesh is not None else "")
            if asset != expected_mesh_asset_path:
                reasons.append("UNAPPROVED_NATIVE_SKELETAL_MESH_IDENTITY")
            else:
                result["native_skeletal_mesh_asset_path"] = asset
            relative = component.get_relative_transform()
            relative_xyz = _vec3(relative.translation, "relative component translation")
            relative_scale = _vec3(relative.scale3d, "relative component scale")
            quaternion = tuple(float(getattr(relative.rotation, a))
                               for a in ("x", "y", "z", "w"))
            if (not all(math.isfinite(v) for v in quaternion)
                    or abs(sum(v * v for v in quaternion) - 1) > 0.02):
                reasons.append("INVALID_RELATIVE_COMPONENT_QUATERNION")
            elif 2 * math.degrees(math.acos(min(1, abs(quaternion[3])))) > 0.25:
                reasons.append("COMPONENT_RELATIVE_ROTATION_OWNS_MESH_FACING")
            if (math.dist(relative_xyz, (0, 0, 0)) > 0.1
                    or max(abs(v - 1) for v in relative_scale) > 0.01):
                reasons.append("COMPONENT_RELATIVE_TRANSLATION_OR_SCALE")
            # An animation mode can drive bones independently of an actor
            # base rotation, even in a scene with no authored tracks.
            # The editor's current mode alone does not prove zero root motion.
            try:
                mode = str(component.get_editor_property("animation_mode"))
                if not mode or len(mode) > 128:
                    raise ValueError("Unrecognized animation mode.")
                result["native_skeletal_animation_mode"] = mode
            except (AttributeError, TypeError, ValueError, RuntimeError):
                reasons.append("SKELETAL_ANIMATION_MODE_UNOBSERVABLE")
            try:
                physics = component.is_simulating_physics()
                if type(physics) is not bool:
                    raise ValueError("Physics result not Boolean.")
                if physics:
                    reasons.append("SKELETAL_COMPONENT_PHYSICS_OWNS_POSE")
            except (AttributeError, TypeError, ValueError, RuntimeError):
                reasons.append("SKELETAL_PHYSICS_MODE_UNOBSERVABLE")
        kinds = _track_kinds(api, sequence)
        result["native_track_types"] = sorted(set(kinds))
        if any(kind not in ALLOWED_READONLY_TRACKS for kind in kinds):
            # Unknown/ControlRig, skeletal animation, 3D transforms, shots,
            # constraints, nested sequences and arbitrary property channels
            # all can own an actor or mesh orientation, directly or indirectly.
            reasons.append("NATIVE_TRACK_OR_ANIMATION_OWNER_NOT_ISOLATED")
    except CharacterFacingOwnershipError as exc:
        reasons.append(str(exc))
    except (AttributeError, TypeError, ValueError, RuntimeError) as exc:
        reasons.append("INCOMPLETE_NATIVE_CHARACTER_HIERARCHY_OR_COMPONENT_READBACK")
    result["blocking_reasons"] = sorted(set(reasons))
    if result["blocking_reasons"]:
        result["status"] = "BLOCKED_UNVERIFIED_OWNER"
    else:
        # Merely says no *observed* conflicting native track/attachment/basis.
        # It is NOT evidence that imported skin geometry, animation blueprint,
        # root motion or source/target orientation are equivalent.
        result["status"] = "STATIC_NATIVE_OWNER_CANDIDATE_REQUIRES_SOURCE_PROOF"
        result["owner_hypothesis"] = "STATIC_ACTOR_BASE_POSSIBLE_UNPROVEN"
    return result
