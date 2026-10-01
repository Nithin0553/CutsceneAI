from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .planner import build_transfer_plan, load_json

Json = dict[str, Any]


class UnrealGenerationError(RuntimeError):
    """Raised when the Unreal editor cannot realize a deterministic transfer plan."""


def generate_from_files(
    csir_path: str | Path,
    unity_source_path: str | Path,
    mapping_path: str | Path,
    *,
    plan_output_path: str | Path | None = None,
    open_in_sequencer: bool = True,
) -> Json:
    """Generate a staged Unreal Level Sequence from Benchmark 001 source files.

    This function must run inside Unreal Editor with the Python Editor Script and
    Sequencer Scripting plugins enabled. It never overwrites an existing target
    Level Sequence.
    """
    csir = load_json(csir_path)
    unity_source = load_json(unity_source_path)
    mapping = load_json(mapping_path)
    plan = build_transfer_plan(csir, unity_source, mapping)

    if plan_output_path is not None:
        output = Path(plan_output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(plan, indent=2), encoding="utf-8")

    unreal = _import_unreal()
    sequence = _create_staging_sequence(unreal, plan)

    try:
        binding_map = _create_bindings(unreal, sequence, plan)
        _apply_operations(unreal, sequence, plan, binding_map)
        _save_sequence(unreal, sequence)
        if open_in_sequencer:
            unreal.LevelSequenceEditorBlueprintLibrary.open_level_sequence(sequence)
            unreal.LevelSequenceEditorBlueprintLibrary.refresh_current_level_sequence()
    except Exception:
        # Keep the staging asset for forensic inspection. Nothing outside the newly
        # created sequence is modified by this adapter.
        raise

    sequence_asset_path = _sequence_asset_path(plan)
    return {
        "status": "STAGED",
        "sequence_asset_path": sequence_asset_path,
        "transfer_id": plan["transfer_id"],
        "binding_count": len(binding_map),
        "operation_count": len(plan["operations"]),
        "warnings": plan["warnings"],
        "quantization": plan["quantization"],
    }


def _import_unreal() -> Any:
    try:
        import unreal  # type: ignore[import-not-found]
    except ImportError as exc:
        raise UnrealGenerationError(
            "The Unreal adapter must be run from Unreal Editor's Python environment."
        ) from exc
    return unreal


def _create_staging_sequence(unreal: Any, plan: Json) -> Any:
    target = plan["target"]
    asset_path = _sequence_asset_path(plan)
    if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
        raise UnrealGenerationError(
            f"Refusing to overwrite existing staging sequence: {asset_path}. "
            "Delete or rename the old staging asset, then retry."
        )

    level_path = str(target.get("level_path", ""))
    if level_path:
        if not unreal.EditorAssetLibrary.does_asset_exist(level_path):
            raise UnrealGenerationError(
                f"Target level does not exist: {level_path}. Prepare the Benchmark 001 "
                "environment first or remove level_path from the mapping."
            )
        unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level(level_path)

    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    sequence = asset_tools.create_asset(
        asset_name=target["sequence_name"],
        package_path=target["sequence_path"],
        asset_class=unreal.LevelSequence,
        factory=unreal.LevelSequenceFactoryNew(),
    )
    if sequence is None:
        raise UnrealGenerationError(f"Failed to create Level Sequence {asset_path}.")

    display_rate = target["display_rate"]
    tick_resolution = target["tick_resolution"]
    sequence.set_display_rate(
        unreal.FrameRate(
            numerator=int(display_rate["numerator"]),
            denominator=int(display_rate["denominator"]),
        )
    )
    sequence.set_tick_resolution_directly(
        unreal.FrameRate(
            numerator=int(tick_resolution["numerator"]),
            denominator=int(tick_resolution["denominator"]),
        )
    )
    sequence.set_playback_start_seconds(float(target["playback_start_seconds"]))
    sequence.set_playback_end_seconds(float(target["playback_end_seconds"]))
    sequence.set_view_range_start(float(target["playback_start_seconds"]))
    sequence.set_view_range_end(float(target["playback_end_seconds"]))
    sequence.set_work_range_start(float(target["playback_start_seconds"]))
    sequence.set_work_range_end(float(target["playback_end_seconds"]))
    return sequence


def _create_bindings(unreal: Any, sequence: Any, plan: Json) -> dict[str, Any]:
    subsystem = unreal.get_editor_subsystem(unreal.LevelSequenceEditorSubsystem)
    bindings: dict[str, Any] = {}

    for spec in plan["bindings"]:
        source_entity_id = spec["source_entity_id"]
        kind = spec["kind"]
        if kind == "skeletal_mesh":
            binding = subsystem.add_spawnable_from_class(sequence, unreal.SkeletalMeshActor)
            template = binding.get_object_template()
            mesh = _load_required_asset(unreal, spec["asset_path"], "skeletal mesh")
            component = template.get_skeletal_mesh_component()
            component.set_skeletal_mesh_asset(mesh)
        elif kind == "static_mesh":
            binding = subsystem.add_spawnable_from_class(sequence, unreal.StaticMeshActor)
            template = binding.get_object_template()
            mesh = _load_required_asset(unreal, spec["asset_path"], "static mesh")
            component = template.get_editor_property("static_mesh_component")
            component.set_static_mesh(mesh)
        elif kind == "camera":
            binding = subsystem.add_spawnable_from_class(sequence, unreal.CameraActor)
            template = binding.get_object_template()
        else:
            raise UnrealGenerationError(
                f"Unsupported Benchmark 001 binding kind {kind!r} for {spec['source_name']!r}."
            )

        if binding is None:
            raise UnrealGenerationError(f"Failed to create binding for {spec['source_name']!r}.")
        binding.set_display_name(spec["source_name"])
        bindings[source_entity_id] = binding
        _apply_template_transform(unreal, template, spec["initial_transform"])

    return bindings


def _apply_template_transform(unreal: Any, template: Any, transform: Json) -> None:
    location = transform["location_cm"]
    rotation = transform["rotation_quaternion"]
    scale = transform["scale"]
    quaternion = unreal.Quat(
        float(rotation["x"]),
        float(rotation["y"]),
        float(rotation["z"]),
        float(rotation["w"]),
    )
    template.set_actor_transform(
        unreal.Transform(
            location=unreal.Vector(
                float(location["x"]),
                float(location["y"]),
                float(location["z"]),
            ),
            rotation=quaternion,
            scale=unreal.Vector(
                float(scale["x"]),
                float(scale["y"]),
                float(scale["z"]),
            ),
        ),
        sweep=False,
        teleport=True,
    )


def _apply_operations(
    unreal: Any,
    sequence: Any,
    plan: Json,
    bindings: dict[str, Any],
) -> None:
    camera_cut_track = None
    audio_track = None

    for operation in plan["operations"]:
        operation_type = operation["type"]
        if operation_type == "skeletal_animation":
            _add_skeletal_animation(unreal, bindings, operation)
        elif operation_type == "transform_animation":
            _add_transform_animation(unreal, sequence, bindings, operation)
        elif operation_type == "camera_fov":
            _add_camera_fov(unreal, sequence, bindings, operation)
        elif operation_type == "camera_cut":
            if camera_cut_track is None:
                camera_cut_track = sequence.add_track(unreal.MovieSceneCameraCutTrack)
            _add_camera_cut(unreal, sequence, bindings, camera_cut_track, operation)
        elif operation_type == "audio":
            if audio_track is None:
                audio_track = sequence.add_track(unreal.MovieSceneAudioTrack)
            _add_audio(unreal, audio_track, operation)
        elif operation_type == "marker":
            _add_marker(unreal, sequence, operation)
        else:
            raise UnrealGenerationError(f"Unknown transfer-plan operation: {operation_type!r}")


def _add_skeletal_animation(unreal: Any, bindings: dict[str, Any], operation: Json) -> None:
    binding = _require_binding(bindings, operation)
    animation = _load_required_asset(unreal, operation["target_asset_path"], "animation")
    track = binding.add_track(unreal.MovieSceneSkeletalAnimationTrack)
    section = track.add_section()
    section.set_range_seconds(
        float(operation["start_seconds"]),
        float(operation["end_seconds"]),
    )
    params = section.get_editor_property("params")
    params.set_editor_property("animation", animation)
    if operation.get("clip_in_seconds", 0.0):
        _try_set_editor_property(
            params,
            "start_frame_offset",
            unreal.FrameNumber(int(round(float(operation["clip_in_seconds"]) * 1_000_000))),
        )
    _try_set_editor_property(params, "play_rate", float(operation.get("time_scale", 1.0)))


def _add_transform_animation(
    unreal: Any,
    sequence: Any,
    bindings: dict[str, Any],
    operation: Json,
) -> None:
    binding = _require_binding(bindings, operation)
    track = binding.add_track(unreal.MovieScene3DTransformTrack)
    section = track.add_section()
    section.set_range_seconds(
        float(operation["section_start_seconds"]),
        float(operation["section_end_seconds"]),
    )

    channels = _channels_by_name(section)
    defaults = operation["defaults"]
    location = defaults["location_cm"]
    rotation = _quat_json_to_rotator(unreal, defaults["rotation_quaternion"])
    scale = defaults["scale"]

    _set_channel_default(channels, "Location.X", float(location["x"]))
    _set_channel_default(channels, "Location.Y", float(location["y"]))
    _set_channel_default(channels, "Location.Z", float(location["z"]))
    _set_channel_default(channels, "Rotation.X", float(rotation.roll))
    _set_channel_default(channels, "Rotation.Y", float(rotation.pitch))
    _set_channel_default(channels, "Rotation.Z", float(rotation.yaw))
    _set_channel_default(channels, "Scale.X", float(scale["x"]))
    _set_channel_default(channels, "Scale.Y", float(scale["y"]))
    _set_channel_default(channels, "Scale.Z", float(scale["z"]))

    for key in operation.get("location_keys", []):
        value = key["location_cm"]
        _add_channel_key(unreal, channels, "Location.X", key["tick"], value["x"])
        _add_channel_key(unreal, channels, "Location.Y", key["tick"], value["y"])
        _add_channel_key(unreal, channels, "Location.Z", key["tick"], value["z"])

    for key in operation.get("rotation_keys", []):
        rotator = _quat_json_to_rotator(unreal, key["rotation_quaternion"])
        _add_channel_key(unreal, channels, "Rotation.X", key["tick"], rotator.roll)
        _add_channel_key(unreal, channels, "Rotation.Y", key["tick"], rotator.pitch)
        _add_channel_key(unreal, channels, "Rotation.Z", key["tick"], rotator.yaw)


def _add_camera_fov(
    unreal: Any,
    sequence: Any,
    bindings: dict[str, Any],
    operation: Json,
) -> None:
    actor_binding = _require_binding(bindings, operation)
    actor_template = actor_binding.get_object_template()
    camera_component = actor_template.get_editor_property("camera_component")
    component_binding = sequence.add_possessable(camera_component)
    component_binding.set_parent(actor_binding)
    component_binding.set_display_name("CameraComponent")

    track = component_binding.add_track(unreal.MovieSceneFloatTrack)
    track.set_property_name_and_path("FieldOfView", "FieldOfView")
    section = track.add_section()
    keys = operation.get("keys", [])
    if not keys:
        return
    section.set_range_seconds(float(keys[0]["time_seconds"]), float(keys[-1]["time_seconds"]))
    channels = section.get_all_channels()
    if not channels:
        raise UnrealGenerationError("Camera FieldOfView track did not expose a scripting channel.")
    channel = channels[0]
    channel.set_default(float(keys[0]["value"]))
    camera_component.set_editor_property("field_of_view", float(keys[0]["value"]))
    for key in keys:
        channel.add_key(
            unreal.FrameNumber(int(key["tick"])),
            float(key["value"]),
            time_unit=unreal.MovieSceneTimeUnit.TICK_RESOLUTION,
            interpolation=unreal.MovieSceneKeyInterpolation.LINEAR,
        )


def _add_camera_cut(
    unreal: Any,
    sequence: Any,
    bindings: dict[str, Any],
    camera_cut_track: Any,
    operation: Json,
) -> None:
    binding = _require_binding(bindings, operation)
    section = camera_cut_track.add_section()
    section.set_range_seconds(
        float(operation["start_seconds"]),
        float(operation["end_seconds"]),
    )
    section.set_camera_binding_id(sequence.get_binding_id(binding))


def _add_audio(unreal: Any, audio_track: Any, operation: Json) -> None:
    sound = _load_required_asset(unreal, operation["target_asset_path"], "audio")
    section = audio_track.add_section()
    section.set_sound(sound)
    section.set_range_seconds(
        float(operation["start_seconds"]),
        float(operation["end_seconds"]),
    )
    _try_set_editor_property(section, "start_offset", float(operation.get("source_offset_seconds", 0.0)))
    _try_set_editor_property(section, "looping", bool(operation.get("loop", False)))


def _add_marker(unreal: Any, sequence: Any, operation: Json) -> None:
    marked_frame = unreal.MovieSceneMarkedFrame(
        frame_number=unreal.FrameNumber(int(operation["tick"])),
        label=str(operation["label"]),
    )
    sequence.add_marked_frame_to_sequence(
        marked_frame,
        unreal.MovieSceneTimeUnit.TICK_RESOLUTION,
    )


def _channels_by_name(section: Any) -> dict[str, Any]:
    channels: dict[str, Any] = {}
    for channel in section.get_all_channels():
        name = str(channel.get_editor_property("channel_name"))
        channels[name] = channel
    missing = {
        "Location.X",
        "Location.Y",
        "Location.Z",
        "Rotation.X",
        "Rotation.Y",
        "Rotation.Z",
        "Scale.X",
        "Scale.Y",
        "Scale.Z",
    } - channels.keys()
    if missing:
        raise UnrealGenerationError(
            "Transform section is missing expected Sequencer channels: "
            + ", ".join(sorted(missing))
        )
    return channels


def _set_channel_default(channels: dict[str, Any], name: str, value: float) -> None:
    channels[name].set_default(value)


def _add_channel_key(
    unreal: Any,
    channels: dict[str, Any],
    name: str,
    tick: int,
    value: float,
) -> None:
    channels[name].add_key(
        unreal.FrameNumber(int(tick)),
        float(value),
        time_unit=unreal.MovieSceneTimeUnit.TICK_RESOLUTION,
        interpolation=unreal.MovieSceneKeyInterpolation.LINEAR,
    )


def _quat_json_to_rotator(unreal: Any, value: Json) -> Any:
    quaternion = unreal.Quat(
        float(value["x"]),
        float(value["y"]),
        float(value["z"]),
        float(value["w"]),
    )
    return quaternion.rotator()


def _load_required_asset(unreal: Any, path: str, label: str) -> Any:
    if not path:
        raise UnrealGenerationError(f"Missing target {label} asset path in mapping.")
    asset = unreal.load_asset(path)
    if asset is None:
        raise UnrealGenerationError(f"Could not load target {label} asset: {path}")
    return asset


def _require_binding(bindings: dict[str, Any], operation: Json) -> Any:
    entity_id = operation["binding_entity_id"]
    try:
        return bindings[entity_id]
    except KeyError as exc:
        raise UnrealGenerationError(f"No generated binding for source entity {entity_id!r}.") from exc


def _try_set_editor_property(obj: Any, name: str, value: Any) -> bool:
    try:
        obj.set_editor_property(name, value)
    except Exception:
        return False
    return True


def _save_sequence(unreal: Any, sequence: Any) -> None:
    if not unreal.EditorAssetLibrary.save_loaded_asset(sequence, only_if_is_dirty=False):
        raise UnrealGenerationError(f"Failed to save generated Level Sequence {sequence.get_path_name()}.")


def _sequence_asset_path(plan: Json) -> str:
    target = plan["target"]
    package_path = str(target["sequence_path"]).rstrip("/")
    return f"{package_path}/{target['sequence_name']}"
