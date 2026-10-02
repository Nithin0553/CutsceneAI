"""Read back a generated Unreal Level Sequence into canonical validation data.

The readback is intentionally independent from the generation request. It inspects the
saved Level Sequence, its actual bindings/tracks/sections/keys, and the mapped level
actors. Numeric transforms are converted back into CutSceneAI canonical space.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import unreal

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import readback_math
import unreal_compat


class UnrealReadbackError(RuntimeError):
    pass


def _editor_property(value: Any, name: str, default: Any = None) -> Any:
    getter = getattr(value, "get_editor_property", None)
    if not callable(getter):
        return default
    try:
        return getter(name)
    except Exception:
        return default


def _class_name(value: Any) -> str:
    get_class = getattr(value, "get_class", None)
    if callable(get_class):
        try:
            unreal_class = get_class()
            get_name = getattr(unreal_class, "get_name", None)
            if callable(get_name):
                return str(get_name())
        except Exception:
            pass
    return type(value).__name__


def _frame_rate(rate: Any) -> dict[str, int]:
    numerator = getattr(rate, "numerator", None)
    denominator = getattr(rate, "denominator", None)
    if numerator is None:
        numerator = _editor_property(rate, "numerator")
    if denominator is None:
        denominator = _editor_property(rate, "denominator")
    return {"numerator": int(numerator), "denominator": int(denominator)}


def _frame_number_value(value: Any) -> int:
    if isinstance(value, int):
        return int(value)
    raw = getattr(value, "value", None)
    if raw is not None:
        return int(raw)
    raw = _editor_property(value, "value")
    if raw is not None:
        return int(raw)
    return int(value)


def _frame_time_value(value: Any) -> int:
    frame_number = getattr(value, "frame_number", None)
    if frame_number is None:
        frame_number = _editor_property(value, "frame_number")
    if frame_number is not None:
        return _frame_number_value(frame_number)
    return _frame_number_value(value)


def _section_range(section: Any) -> tuple[int, int]:
    start = getattr(section, "get_start_frame", None)
    end = getattr(section, "get_end_frame", None)
    if callable(start) and callable(end):
        return int(start()), int(end())
    extensions = getattr(unreal, "MovieSceneSectionExtensions", None)
    if extensions is None:
        raise UnrealReadbackError("MovieSceneSectionExtensions unavailable")
    return int(extensions.get_start_frame(section)), int(extensions.get_end_frame(section))


def _sections(track: Any) -> list[Any]:
    getter = getattr(track, "get_sections", None)
    if callable(getter):
        return list(getter())
    extensions = getattr(unreal, "MovieSceneTrackExtensions", None)
    extension_getter = getattr(extensions, "get_sections", None) if extensions else None
    if callable(extension_getter):
        return list(extension_getter(track))
    raise UnrealReadbackError(f"Cannot enumerate sections for {_class_name(track)}")


def _bindings(sequence: Any) -> list[Any]:
    getter = getattr(sequence, "get_bindings", None)
    if callable(getter):
        return list(getter())
    extensions = getattr(unreal, "MovieSceneSequenceExtensions", None)
    extension_getter = getattr(extensions, "get_bindings", None) if extensions else None
    if callable(extension_getter):
        return list(extension_getter(sequence))
    raise UnrealReadbackError("Cannot enumerate sequence bindings")


def _root_tracks(sequence: Any) -> list[Any]:
    getter = getattr(sequence, "get_tracks", None)
    if callable(getter):
        return list(getter())
    extensions = getattr(unreal, "MovieSceneSequenceExtensions", None)
    extension_getter = getattr(extensions, "get_tracks", None) if extensions else None
    if callable(extension_getter):
        return list(extension_getter(sequence))
    raise UnrealReadbackError("Cannot enumerate root sequence tracks")


def _binding_tracks(binding: Any) -> list[Any]:
    getter = getattr(binding, "get_tracks", None)
    if callable(getter):
        return list(getter())
    extensions = getattr(unreal, "MovieSceneBindingExtensions", None)
    extension_getter = getattr(extensions, "get_tracks", None) if extensions else None
    if callable(extension_getter):
        return list(extension_getter(binding))
    raise UnrealReadbackError("Cannot enumerate binding tracks")


def _binding_name(binding: Any) -> str:
    getter = getattr(binding, "get_name", None)
    if callable(getter):
        return str(getter())
    extensions = getattr(unreal, "MovieSceneBindingExtensions", None)
    extension_getter = getattr(extensions, "get_name", None) if extensions else None
    if callable(extension_getter):
        return str(extension_getter(binding))
    return ""


def _binding_guid(binding: Any) -> Any:
    getter = getattr(binding, "get_id", None)
    if callable(getter):
        return getter()
    extensions = getattr(unreal, "MovieSceneBindingExtensions", None)
    extension_getter = getattr(extensions, "get_id", None) if extensions else None
    if callable(extension_getter):
        return extension_getter(binding)
    return None


def _guid_key(value: Any) -> str:
    if value is None:
        return ""
    components: list[str] = []
    for field in ("a", "b", "c", "d"):
        component = getattr(value, field, None)
        if component is None:
            component = _editor_property(value, field)
        if component is not None:
            components.append(f"{int(component):08x}")
    return "".join(components).lower() if len(components) == 4 else str(value).lower()


def _object_binding_guid(binding_id: Any) -> str:
    getter = getattr(binding_id, "get_guid", None)
    if callable(getter):
        try:
            return _guid_key(getter())
        except Exception:
            pass
    guid = _editor_property(binding_id, "guid")
    return _guid_key(guid)


def _find_actor(label: str) -> Any:
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    matches = [
        actor for actor in subsystem.get_all_level_actors()
        if actor.get_actor_label() == label
    ]
    if len(matches) != 1:
        raise UnrealReadbackError(
            f"Expected one actor labelled '{label}', found {len(matches)}"
        )
    return matches[0]


def _canonical_actor_transform(actor: Any) -> dict[str, list[float]]:
    location = actor.get_actor_location()
    rotation = actor.get_actor_rotation()
    scale = actor.get_actor_scale3d()
    return readback_math.target_transform_to_canonical(
        (float(location.x), float(location.y), float(location.z)),
        (float(rotation.roll), float(rotation.pitch), float(rotation.yaw)),
        (float(scale.x), float(scale.y), float(scale.z)),
    )


def _key_map(channel: Any) -> dict[int, float]:
    result: dict[int, float] = {}
    getter = getattr(channel, "get_keys", None)
    if not callable(getter):
        return result
    for key in getter():
        time = key.get_time(unreal.MovieSceneTimeUnit.DISPLAY_RATE)
        result[_frame_time_value(time)] = float(key.get_value())
    return result


def _transform_track(track: Any) -> dict[str, Any] | None:
    sections = _sections(track)
    if not sections:
        return None
    section = sections[0]
    channels = unreal_compat.get_section_channels(section)
    if len(channels) < 6:
        raise UnrealReadbackError(
            f"Transform section exposed {len(channels)} channels; expected >= 6"
        )
    maps = [_key_map(channel) for channel in channels[:6]]
    frames = sorted(set().union(*(mapping.keys() for mapping in maps)))
    keys: list[dict[str, Any]] = []
    for frame in frames:
        values = [mapping.get(frame) for mapping in maps]
        if any(value is None for value in values):
            raise UnrealReadbackError(
                f"Transform channels do not share frame {frame}; cannot canonicalize safely"
            )
        location = (float(values[0]), float(values[1]), float(values[2]))
        rpy = (float(values[3]), float(values[4]), float(values[5]))
        canonical = readback_math.target_transform_to_canonical(
            location,
            rpy,
            (1.0, 1.0, 1.0),
        )
        keys.append(
            {
                "frame": frame,
                "position_m": canonical["position_m"],
                "rotation_xyzw": canonical["rotation_xyzw"],
            }
        )
    return {"kind": "transform", "keys": keys}


def _asset_path(value: Any) -> str:
    if value is None:
        return ""
    getter = getattr(value, "get_path_name", None)
    if callable(getter):
        path = str(getter())
        # Normalize /Game/Foo.Bar -> /Game/Foo for comparison with mapping paths.
        if "." in path and path.startswith("/Game/"):
            package, object_name = path.rsplit(".", 1)
            if package.rsplit("/", 1)[-1] == object_name:
                return package
        return path
    return str(value)


def _fixed_play_rate(params: Any) -> float:
    play_rate = _editor_property(params, "play_rate", 1.0)
    if isinstance(play_rate, (int, float)):
        return float(play_rate)
    getter = getattr(play_rate, "to_fixed_play_rate", None)
    if callable(getter):
        try:
            return float(getter())
        except Exception:
            pass
    extensions = getattr(unreal, "MovieSceneTimeWarpExtensions", None)
    extension_getter = getattr(extensions, "to_fixed_play_rate", None) if extensions else None
    if callable(extension_getter):
        try:
            return float(extension_getter(play_rate))
        except Exception:
            pass
    return 1.0


def _matrix_vector(matrix: list[list[float]], vector: tuple[float, float, float]) -> list[float]:
    return [
        sum(float(matrix[row][col]) * float(vector[col]) for col in range(3))
        for row in range(3)
    ]


def _skeletal_track(
    track: Any,
    actor: Any | None,
    display_rate: dict[str, int],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    fps = float(display_rate["numerator"]) / float(display_rate["denominator"])
    for section in _sections(track):
        start_frame, end_frame = _section_range(section)
        params = _editor_property(section, "params")
        animation = _editor_property(params, "animation") if params is not None else None
        item: dict[str, Any] = {
            "kind": "skeletal_animation",
            "start_frame": start_frame,
            "end_frame": end_frame,
            "asset_path": _asset_path(animation),
            "post_roll_frames": int(
                section.get_post_roll_frames()
                if callable(getattr(section, "get_post_roll_frames", None))
                else _frame_number_value(_editor_property(section, "post_roll_frames", 0))
            ),
            "play_rate": _fixed_play_rate(params) if params is not None else 1.0,
        }

        if animation is not None and actor is not None:
            duration_seconds = max(0.0, (end_frame - start_frame) / fps)
            try:
                local_delta, strategy = unreal_compat.extract_animation_root_delta_cm(
                    animation,
                    0.0,
                    duration_seconds * float(item["play_rate"]),
                )
                rotation = actor.get_actor_rotation()
                matrix = readback_math.unreal_rpy_to_matrix(
                    float(rotation.roll),
                    float(rotation.pitch),
                    float(rotation.yaw),
                )
                item["effective_root_delta_cm"] = _matrix_vector(matrix, local_delta)
                item["root_motion_sampling_strategy"] = strategy
            except Exception as exc:
                item["root_motion_readback_error"] = str(exc)

        result.append(item)
    return result


def _camera_component_for_actor(actor: Any) -> Any:
    component, _strategy = unreal_compat.resolve_camera_component(actor)
    return component


def _camera_state(actor: Any, target_aspect: float) -> dict[str, float]:
    component = _camera_component_for_actor(actor)
    cine_type = getattr(unreal, "CineCameraComponent", None)
    if cine_type is not None and isinstance(component, cine_type):
        filmback = _editor_property(component, "filmback")
        sensor_height = _editor_property(filmback, "sensor_height")
        focal_length = _editor_property(component, "current_focal_length")
        vertical = readback_math.vertical_fov_from_focal_length(
            float(sensor_height),
            float(focal_length),
        )
    else:
        horizontal = _editor_property(component, "field_of_view")
        vertical = readback_math.vertical_fov_from_horizontal(
            float(horizontal),
            float(target_aspect),
        )
    return {
        "vertical_fov_degrees": float(vertical),
        "target_output_aspect": float(target_aspect),
    }


def _editor_world() -> Any:
    subsystem_type = getattr(unreal, "UnrealEditorSubsystem", None)
    if subsystem_type is not None:
        try:
            subsystem = unreal.get_editor_subsystem(subsystem_type)
            getter = getattr(subsystem, "get_editor_world", None)
            if callable(getter):
                return getter()
        except Exception:
            pass
    library = getattr(unreal, "EditorLevelLibrary", None)
    getter = getattr(library, "get_editor_world", None) if library else None
    if callable(getter):
        return getter()
    return None


def _bound_object(sequence: Any, binding: Any) -> Any | None:
    world = _editor_world()
    extensions = getattr(unreal, "MovieSceneSequenceExtensions", None)
    locator = getattr(extensions, "locate_bound_objects", None) if extensions else None
    if callable(locator) and world is not None:
        try:
            objects = list(locator(sequence, binding, world))
            if len(objects) == 1:
                return objects[0]
        except Exception:
            pass
    return None


def _binding_owner_label(sequence: Any, binding: Any) -> str:
    obj = _bound_object(sequence, binding)
    if obj is None:
        return _binding_name(binding)
    actor_label = getattr(obj, "get_actor_label", None)
    if callable(actor_label):
        return str(actor_label())
    owner_getter = getattr(obj, "get_owner", None)
    if callable(owner_getter):
        owner = owner_getter()
        if owner is not None and callable(getattr(owner, "get_actor_label", None)):
            return str(owner.get_actor_label())
    return _binding_name(binding)


def _lens_track(
    track: Any,
    component: Any,
    target_aspect: float,
) -> dict[str, Any] | None:
    sections = _sections(track)
    if not sections:
        return None
    section = sections[0]
    channels = unreal_compat.get_section_channels(section)
    if len(channels) != 1:
        return None

    cine_type = getattr(unreal, "CineCameraComponent", None)
    cine = cine_type is not None and isinstance(component, cine_type)
    sensor_height = None
    if cine:
        filmback = _editor_property(component, "filmback")
        sensor_height = float(_editor_property(filmback, "sensor_height"))

    keys: list[dict[str, Any]] = []
    for frame, value in sorted(_key_map(channels[0]).items()):
        if cine:
            vertical = readback_math.vertical_fov_from_focal_length(
                float(sensor_height),
                float(value),
            )
        else:
            vertical = readback_math.vertical_fov_from_horizontal(
                float(value),
                target_aspect,
            )
        keys.append({"frame": int(frame), "vertical_fov_degrees": float(vertical)})
    return {"kind": "camera_lens", "keys": keys}


def _audio_section(section: Any) -> dict[str, Any]:
    start, end = _section_range(section)
    sound = None
    for name in ("get_sound", "get_playback_sound"):
        getter = getattr(section, name, None)
        if callable(getter):
            try:
                sound = getter()
                if sound is not None:
                    break
            except Exception:
                pass
    if sound is None:
        sound = _editor_property(section, "sound")

    loop = False
    getter = getattr(section, "get_looping", None)
    if callable(getter):
        try:
            loop = bool(getter())
        except Exception:
            pass
    else:
        loop = bool(_editor_property(section, "looping", False))

    return {
        "start_frame": start,
        "end_frame": end,
        "asset_path": _asset_path(sound),
        "loop": loop,
    }


def _marked_frames(sequence: Any) -> list[dict[str, Any]]:
    frames: list[Any] = []
    getter = getattr(sequence, "get_marked_frames_from_sequence", None)
    if callable(getter):
        try:
            frames = list(getter(unreal.MovieSceneTimeUnit.DISPLAY_RATE))
        except Exception:
            frames = []
    if not frames:
        extensions = getattr(unreal, "MovieSceneSequenceExtensions", None)
        extension_getter = (
            getattr(extensions, "get_marked_frames_from_sequence", None)
            if extensions else None
        )
        if callable(extension_getter):
            frames = list(
                extension_getter(sequence, unreal.MovieSceneTimeUnit.DISPLAY_RATE)
            )

    result: list[dict[str, Any]] = []
    for marked in frames:
        frame = _editor_property(marked, "frame_number")
        label = _editor_property(marked, "label", "")
        result.append({"frame": _frame_number_value(frame), "label": str(label)})
    return result


def readback(
    sequence_asset_path: str,
    mapping: dict[str, Any],
) -> dict[str, Any]:
    sequence = unreal.load_asset(sequence_asset_path)
    if sequence is None:
        raise UnrealReadbackError(f"Level Sequence not found: {sequence_asset_path}")

    # Evaluate frame zero so static camera state and prepared actor transforms are read
    # from a deterministic sequence position rather than the user's current scrub frame.
    unreal.LevelSequenceEditorBlueprintLibrary.open_level_sequence(sequence)
    set_time = getattr(unreal.LevelSequenceEditorBlueprintLibrary, "set_current_time", None)
    if callable(set_time):
        try:
            set_time(0)
        except Exception:
            pass

    rate = _frame_rate(sequence.get_display_rate())
    start_frame = int(sequence.get_playback_start())
    end_frame = int(sequence.get_playback_end())

    output = mapping.get("output_resolution", [1920, 1080])
    width, height = int(output[0]), int(output[1])
    target_aspect = float(width) / float(height)

    sequence_bindings = _bindings(sequence)
    guid_to_name = {
        _guid_key(_binding_guid(binding)): _binding_name(binding)
        for binding in sequence_bindings
    }

    mapping_labels = {
        str(entry.get("actor_label"))
        for entry in mapping.get("entities", {}).values()
        if isinstance(entry, dict) and entry.get("actor_label")
    }

    binding_records: dict[str, dict[str, Any]] = {}
    for binding in sequence_bindings:
        name = _binding_name(binding)
        owner_label = _binding_owner_label(sequence, binding)
        record_name = owner_label if owner_label in mapping_labels else name
        record = binding_records.setdefault(
            record_name,
            {
                "name": record_name,
                "binding_id": _guid_key(_binding_guid(binding)),
                "tracks": [],
            },
        )

        actor = None
        if record_name in mapping_labels:
            try:
                actor = _find_actor(record_name)
            except UnrealReadbackError:
                actor = None

        bound_object = _bound_object(sequence, binding)

        for track in _binding_tracks(binding):
            if isinstance(track, unreal.MovieScene3DTransformTrack):
                item = _transform_track(track)
                if item is not None:
                    record["tracks"].append(item)
            elif isinstance(track, unreal.MovieSceneSkeletalAnimationTrack):
                record["tracks"].extend(_skeletal_track(track, actor, rate))
            elif isinstance(track, unreal.MovieSceneFloatTrack):
                component = bound_object
                if component is None and actor is not None:
                    try:
                        component = _camera_component_for_actor(actor)
                    except Exception:
                        component = None
                if component is not None:
                    item = _lens_track(track, component, target_aspect)
                    if item is not None:
                        record["tracks"].append(item)

    # Enrich mapped actor bindings with read-back actor/camera state. Static transforms
    # are recorded only for actors without a generated transform track; dynamic transform
    # parity comes from actual Sequencer keys.
    for label in sorted(mapping_labels):
        record = binding_records.setdefault(
            label,
            {"name": label, "binding_id": "", "tracks": []},
        )
        actor = _find_actor(label)
        has_transform_track = any(
            track.get("kind") == "transform" for track in record["tracks"]
        )
        has_skeletal_track = any(
            track.get("kind") == "skeletal_animation" for track in record["tracks"]
        )
        if not has_transform_track and not has_skeletal_track:
            record["canonical_world_transform"] = _canonical_actor_transform(actor)

        if isinstance(actor, (unreal.CameraActor, unreal.CineCameraActor)):
            record["camera_state"] = _camera_state(actor, target_aspect)

    camera_cuts: list[dict[str, Any]] = []
    audio_sections: list[dict[str, Any]] = []
    for track in _root_tracks(sequence):
        if isinstance(track, unreal.MovieSceneCameraCutTrack):
            for section in _sections(track):
                start, end = _section_range(section)
                binding_id = section.get_camera_binding_id()
                camera_guid = _object_binding_guid(binding_id)
                camera_cuts.append(
                    {
                        "start_frame": start,
                        "end_frame": end,
                        "camera_binding": guid_to_name.get(camera_guid, camera_guid),
                    }
                )
        elif isinstance(track, unreal.MovieSceneAudioTrack):
            for section in _sections(track):
                audio_sections.append(_audio_section(section))

    return {
        "schema_version": "0.1.0",
        "engine": {
            "name": "unreal",
            "version": unreal_compat.engine_version(),
        },
        "sequence_asset_path": sequence_asset_path,
        "display_rate": rate,
        "playback": {
            "start_frame": start_frame,
            "end_frame": end_frame,
        },
        "bindings": list(binding_records.values()),
        "camera_cuts": camera_cuts,
        "audio_sections": audio_sections,
        "markers": _marked_frames(sequence),
    }


def readback_from_files(
    mapping_path: str,
    output_path: str,
    sequence_asset_path: str | None = None,
) -> dict[str, Any]:
    mapping = json.loads(Path(mapping_path).read_text(encoding="utf-8"))
    asset_path = sequence_asset_path or str(
        mapping.get(
            "sequence_asset_path",
            "/Game/CutSceneAI/Benchmark001/LS_Benchmark001",
        )
    )
    snapshot = readback(asset_path, mapping)
    Path(output_path).write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    unreal.log(f"[CutSceneAI] Unreal readback snapshot written: {output_path}")
    return snapshot
