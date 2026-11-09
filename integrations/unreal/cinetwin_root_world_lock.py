"""Opt-in Unreal Editor root-bone world-trajectory bake for staged sequences only.

A source CineTwin skeletal-root observation has an unambiguous world-space
meaning. Reconstruct it by evaluating the target imported animation and
adding an actor translation track with the difference for each exact source
frame. This is explicitly only root POSITION equivalence; retargeting,
joint-level poses and visual quality remain unverified.
"""
from __future__ import annotations

import re
import warnings
from typing import Any


class UnrealRootWorldLockError(RuntimeError):
    pass


def _alias(bone: str) -> str:
    return re.sub(r"\[\d+\]$", "", bone.rsplit("/", 1)[-1]).rsplit(":", 1)[-1].casefold()


def _vector(value: Any) -> tuple[float, float, float]:
    return float(value.x), float(value.y), float(value.z)


def preflight(sequence: Any, actions: list[dict[str, Any]], bindings: dict[str, Any], api: Any) -> None:
    """Reject unsupported rigs/attachments and overlapping actor transform tracks."""
    if not actions:
        return
    if not callable(getattr(api.LevelSequenceEditorBlueprintLibrary, "set_current_time", None)):
        raise UnrealRootWorldLockError("Editor Sequencer frame evaluation API not available.")
    if not callable(getattr(api.LevelSequenceEditorBlueprintLibrary, "open_level_sequence", None)):
        raise UnrealRootWorldLockError("Editor Sequencer open API not available.")
    if not hasattr(api, "MovieScene3DTransformTrack"):
        raise UnrealRootWorldLockError("Editor lacks transform tracks for root corrections.")
    for action in actions:
        name = action["entity_name"]
        if name not in bindings:
            raise UnrealRootWorldLockError("Missing actor binding: " + name)
        actor = bindings[name]["actor"]
        binding = bindings[name]["binding"]
        if actor.get_attach_parent_actor() is not None:
            raise UnrealRootWorldLockError(
                f"Attached skeletal character {name} needs parent-local root policy; "
                "cannot bake a world actor correction."
            )
        if any(isinstance(t, api.MovieScene3DTransformTrack)
               for t in binding.get_tracks()):
            raise UnrealRootWorldLockError(
                f"Existing transform track for {name}: cannot add competing root lock."
            )
        meshes = actor.get_components_by_class(api.SkeletalMeshComponent)
        if len(meshes) != 1:
            raise UnrealRootWorldLockError(
                f"Expected exactly one skeletal mesh component for {name}."
            )
        mesh = meshes[0]
        target_root = str(mesh.get_bone_name(0))
        if _alias(target_root) != action["root_bone_alias"]:
            raise UnrealRootWorldLockError(
                f"Cannot identify the same skeletal root for {name}: "
                f"Unity={action['root_source_bone_id']}, Unreal={target_root}."
            )
        frames = [int(k["frame"]) for k in action["keys"]]
        if not frames or frames != list(range(frames[0], frames[-1] + 1)):
            raise UnrealRootWorldLockError("Root lock keys must be complete consecutive frames.")
        if frames[0] != sequence.get_playback_start():
            raise UnrealRootWorldLockError("Root lock must begin at sequence playback start.")
        if frames[-1] >= sequence.get_playback_end():
            raise UnrealRootWorldLockError("Root lock must exclude playback-end boundary.")


def prepare_corrections(
    sequence: Any,
    actions: list[dict[str, Any]],
    bindings: dict[str, Any],
    api: Any,
) -> list[dict[str, Any]]:
    """Read-only frame evaluation. Restore previous Sequencer editor state."""
    preflight(sequence, actions, bindings, api)
    if not actions:
        return []
    editor = api.LevelSequenceEditorBlueprintLibrary
    previous = editor.get_current_level_sequence()
    previous_time = editor.get_current_time() if previous else None
    generated = []
    try:
        editor.open_level_sequence(sequence)
        for action in actions:
            actor = bindings[action["entity_name"]]["actor"]
            mesh = actor.get_components_by_class(api.SkeletalMeshComponent)[0]
            bone = str(mesh.get_bone_name(0))
            keys = []
            for item in action["keys"]:
                frame = int(item["frame"])
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", DeprecationWarning)
                    editor.set_current_time(frame)
                updater = getattr(editor, "force_update", None)
                if callable(updater):
                    updater()
                bone_xyz = _vector(mesh.get_socket_location(bone))
                actor_xyz = _vector(actor.get_actor_location())
                desired = item["source_root_world_cm"]
                corrected = [
                    actor_xyz[i] + float(desired[i]) - bone_xyz[i]
                    for i in range(3)
                ]
                rotation = actor.get_actor_rotation()
                keys.append({
                    "frame": frame,
                    "location_cm": corrected,
                    "rotation_rpy_degrees": [
                        float(rotation.roll), float(rotation.pitch), float(rotation.yaw)
                    ],
                })
            generated.append({
                "kind": "transform",
                "entity_name": action["entity_name"],
                "actor_label": action["actor_label"],
                "track_name": "CutSceneAI Source-Observed Skeletal Root World Lock",
                "keys": keys,
                "baked_source_curves": True,
                "source_behavior_strategy": "unreal_editor_sampled_skeletal_root_world_lock",
            })
        return generated
    finally:
        # Never persist temporary playhead/editor navigation as research state.
        if previous:
            editor.open_level_sequence(previous)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                editor.set_current_time(previous_time)
        else:
            editor.close_level_sequence()
