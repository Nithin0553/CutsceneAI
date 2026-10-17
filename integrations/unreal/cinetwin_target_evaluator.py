"""Observe *evaluated* Unreal Sequencer actor and bone state at source times.

This is NOT an Unreal CineTwin pose player or an equivalence validator. It
provides independent target observations and reports unmapped source entities.
No target animation, level, or sequence assets are saved or edited.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import unreal

HERE = Path(__file__).resolve().parent
for sibling in (HERE, HERE.parents[1] / "packages" / "cinetwin"):
    if str(sibling) not in sys.path:
        sys.path.insert(0, str(sibling))

import readback_math
import target_observation_plan


class CineTwinTargetObservationError(RuntimeError):
    pass


def _find_actors(bound: list[dict[str, str]]) -> dict[str, Any]:
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    observed = list(subsystem.get_all_level_actors())
    by_label: dict[str, list[Any]] = {}
    for actor in observed:
        by_label.setdefault(str(actor.get_actor_label()), []).append(actor)

    result = {}
    for entry in bound:
        matches = by_label.get(entry["actor_label"], [])
        if len(matches) != 1:
            raise CineTwinTargetObservationError(
                "Target requires exactly one actor with label "
                f"{entry['actor_label']!r}; found {len(matches)}. "
                "Open the mapped target level before observing."
            )
        result[entry["entity_id"]] = matches[0]
    return result


def _skeletal_component(actor: Any) -> Any:
    components = list(actor.get_components_by_class(unreal.SkeletalMeshComponent))
    if len(components) != 1:
        raise CineTwinTargetObservationError(
            f"Actor {actor.get_actor_label()!r} has {len(components)} "
            "skeletal mesh components; provide an explicit component mapping "
            "before target pose evaluation."
        )
    return components[0]


def _rig_structure(component: Any, entity_id: str) -> dict[str, Any]:
    count = int(component.get_num_bones())
    if count <= 0:
        raise CineTwinTargetObservationError(
            f"Mapped rig {entity_id} has no target skeletal bones."
        )
    bones = []
    for index in range(count):
        name = str(component.get_bone_name(index))
        parent = str(component.get_parent_bone(name))
        bones.append({
            "bone_name": name,
            "parent_bone_name": None if parent.lower() == "none" else parent,
        })
    if len(set(bone["bone_name"] for bone in bones)) != len(bones):
        raise CineTwinTargetObservationError(
            "Target skeletal rig contains duplicate bone names: " + entity_id
        )
    return {"entity_id": entity_id, "native_target_bones": bones}


def _actor_transform(actor: Any) -> dict[str, list[float]]:
    location = actor.get_actor_location()
    rotation = actor.get_actor_rotation()
    scale = actor.get_actor_scale3d()
    return readback_math.target_transform_to_canonical(
        (float(location.x), float(location.y), float(location.z)),
        (float(rotation.roll), float(rotation.pitch), float(rotation.yaw)),
        (float(scale.x), float(scale.y), float(scale.z)),
    )


def _bone_state(component: Any, bone_name: str) -> dict[str, Any]:
    # Capture native Unreal orientation explicitly; a Unity/Unreal bone retarget
    # mapping is required before angular pose equivalence can be asserted.
    transform = component.get_bone_transform(
        bone_name, unreal.RelativeTransformSpace.RTS_WORLD
    )
    location = transform.translation
    rotation = transform.rotation
    scale = transform.scale3d
    values = [
        float(location.x), float(location.y), float(location.z),
        float(rotation.x), float(rotation.y), float(rotation.z), float(rotation.w),
        float(scale.x), float(scale.y), float(scale.z),
    ]
    if any(not math.isfinite(value) for value in values):
        raise CineTwinTargetObservationError(
            "Target pose contains non-finite bone transform: " + bone_name
        )
    return {
        "bone_name": bone_name,
        "world_position_m": list(
            readback_math.unreal_position_cm_to_canonical_m(values[:3])
        ),
        "unreal_world_rotation_xyzw": values[3:7],
        "unreal_world_scale_xyz": values[7:10],
    }


def _sequencer_api() -> Any:
    library = unreal.LevelSequenceEditorBlueprintLibrary
    missing = [
        field for field in ("set_global_position", "get_global_position", "force_update")
        if not callable(getattr(library, field, None))
    ]
    if missing:
        raise CineTwinTargetObservationError(
            "Unreal Sequencer lacks required time-precise evaluation functions: "
            + ", ".join(missing)
        )
    if not hasattr(unreal.MovieScenePositionType, "TIME"):
        raise CineTwinTargetObservationError(
            "Unreal does not expose MovieScenePositionType.TIME."
        )
    if not hasattr(unreal.UpdatePositionMethod, "JUMP"):
        raise CineTwinTargetObservationError(
            "Unreal does not expose UpdatePositionMethod.JUMP."
        )
    return library


def _seek(library: Any, time_seconds: float) -> None:
    params = unreal.MovieSceneSequencePlaybackParams(
        time=float(time_seconds),
        position_type=unreal.MovieScenePositionType.TIME,
        update_method=unreal.UpdatePositionMethod.JUMP,
        has_jumped=True,
    )
    library.set_global_position(params, unreal.MovieSceneTimeUnit.DISPLAY_RATE)
    library.force_update()


def run(
    sampling_plan_path: str,
    mapping_path: str,
    sequence_asset_path: str,
    output_path: str,
    *,
    max_samples: int | None = None,
) -> dict[str, Any]:
    plan = json.loads(Path(sampling_plan_path).read_text(encoding="utf-8-sig"))
    mapping = json.loads(Path(mapping_path).read_text(encoding="utf-8-sig"))
    request = target_observation_plan.prepare_observation(
        plan, mapping, max_samples=max_samples
    )
    sequence = unreal.load_asset(sequence_asset_path)
    if sequence is None or not isinstance(sequence, unreal.LevelSequence):
        raise CineTwinTargetObservationError(
            "Could not load Unreal Level Sequence: " + sequence_asset_path
        )
    library = _sequencer_api()
    earlier_sequence = library.get_current_level_sequence()
    earlier_position = None
    opened_for_capture = earlier_sequence is None or (
        earlier_sequence.get_path_name() != sequence.get_path_name()
    )
    if opened_for_capture:
        library.open_level_sequence(sequence)

    try:
        current_sequence = library.get_current_level_sequence()
        if (
            current_sequence is None
            or current_sequence.get_path_name() != sequence.get_path_name()
        ):
            raise CineTwinTargetObservationError(
                "The requested Unreal Level Sequence is not active in Sequencer."
            )
        earlier_position = library.get_global_position()
        actors = _find_actors(request["bound"])
        skeletal_components = {
            entry["entity_id"]: _skeletal_component(actors[entry["entity_id"]])
            for entry in request["skeletal_rigs"]
        }
        rigs = [
            _rig_structure(skeletal_components[entry["entity_id"]], entry["entity_id"])
            for entry in request["skeletal_rigs"]
        ]
        rig_names = {
            rig["entity_id"]: [
                bone["bone_name"] for bone in rig["native_target_bones"]
            ] for rig in rigs
        }
        observations = []
        for time_seconds in request["selected_times_seconds"]:
            _seek(library, time_seconds)
            entities = [
                {
                    "entity_id": entry["entity_id"],
                    "actor_label": entry["actor_label"],
                    "world_transform": _actor_transform(actors[entry["entity_id"]]),
                }
                for entry in request["bound"]
            ]
            skeletal_poses = [
                {
                    "entity_id": rig_id,
                    "bones": [
                        _bone_state(skeletal_components[rig_id], bone_name)
                        for bone_name in names
                    ],
                }
                for rig_id, names in rig_names.items()
            ]
            observations.append({
                "time_seconds": time_seconds,
                "entities": entities,
                "skeletal_poses": skeletal_poses,
            })

        capture = {
            "schema_version": "0.1.0",
            "kind": "cinetwin.target_behavior_observation",
            "cutscene_id": request["cutscene_id"],
            "source": request["source"],
            "target": {
                "engine": "unreal",
                "engine_version": unreal.SystemLibrary.get_engine_version(),
                "sequence_asset_path": sequence.get_path_name(),
            },
            "coverage": {
                "sample_count": len(observations),
                "full_sample_count": request["full_sample_count"],
                "mapped_entity_count": len(request["bound"]),
                "source_entity_count": len(plan["entities"]),
                "unmapped_source_entities": request["missing"],
                "skeletal_rig_count": len(rigs),
                "full_temporal_coverage": (
                    len(observations) == request["full_sample_count"]
                ),
                "pose_semantic_comparison": "NOT_IMPLEMENTED_REQUIRES_BONE_MAPPING",
            },
            "native_rigs": rigs,
            "samples": observations,
            "provenance": {
                "method": "sequencer_jump_force_evaluation",
                "captured_at_utc": datetime.now(timezone.utc).isoformat(),
                "asset_mutation": False,
            },
        }
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(capture, indent=2), encoding="utf-8")
        unreal.log(
            "[CineTwin] Target observations saved: "
            f"{target} (samples={len(observations)}, "
            f"mapped_entities={len(request['bound'])}, "
            f"unmapped_entities={len(request['missing'])}, "
            f"skeletal_rigs={len(rigs)})"
        )
        return capture
    finally:
        # Scrubbing may temporarily alter editor-world actor state. Restore the
        # previous playhead/sequence; never save target assets during capture.
        if earlier_position is not None:
            try:
                library.set_global_position(
                    earlier_position, unreal.MovieSceneTimeUnit.DISPLAY_RATE
                )
                library.force_update()
            except Exception as error:
                unreal.log_warning(
                    "[CineTwin] Could not restore Unreal Sequencer playhead: "
                    + str(error)
                )
        if opened_for_capture and earlier_sequence is not None:
            library.open_level_sequence(earlier_sequence)
        elif opened_for_capture and earlier_sequence is None:
            library.close_level_sequence()
