"""Runtime capability adaptation for the CutSceneAI Unreal adapter.

The adapter must not assume a single Unreal version.  It records the engine version for
provenance, but chooses APIs by feature/capability detection whenever possible.
"""

from __future__ import annotations

import math
from typing import Any

import unreal


class UnrealCompatibilityError(RuntimeError):
    pass


def engine_version() -> str:
    """Return the current Unreal build/version string when the runtime exposes it."""
    library = getattr(unreal, "SystemLibrary", None)
    getter = getattr(library, "get_engine_version", None) if library else None
    if callable(getter):
        try:
            return str(getter())
        except Exception:
            pass
    return "unknown"


def section_channel_strategy() -> str:
    """Describe the best channel API visible in the current Unreal runtime."""
    extensions = getattr(unreal, "MovieSceneSectionExtensions", None)
    extension_get_all = getattr(extensions, "get_all_channels", None) if extensions else None
    if callable(extension_get_all):
        return "MovieSceneSectionExtensions.get_all_channels"

    section_type = getattr(unreal, "MovieScene3DTransformSection", None)
    if section_type is not None and callable(getattr(section_type, "get_all_channels", None)):
        return "section.get_all_channels"
    if section_type is not None and callable(getattr(section_type, "get_channels", None)):
        return "section.get_channels_legacy"
    return "instance_probe"


def play_rate_strategy() -> str:
    variant_type = getattr(unreal, "MovieSceneTimeWarpVariant", None)
    if variant_type is None:
        return "legacy_float"
    if callable(getattr(variant_type, "set_fixed_play_rate", None)):
        return "MovieSceneTimeWarpVariant.set_fixed_play_rate"
    return "MovieSceneTimeWarpVariant.instance_probe"


def animation_root_sampling_strategy() -> str:
    library = getattr(unreal, "AnimationLibrary", None)
    raw = getattr(library, "extract_root_track_transform", None) if library else None
    if callable(raw):
        return "AnimationLibrary.extract_root_track_transform"
    motion = getattr(unreal, "MotionWarpingUtilities", None)
    extract = getattr(motion, "extract_root_motion_from_animation", None) if motion else None
    if callable(extract):
        return "MotionWarpingUtilities.extract_root_motion_from_animation"
    return "unavailable"


def runtime_profile() -> dict[str, str]:
    """Return a compact capability profile for logging and provenance."""
    return {
        "engine_version": engine_version(),
        "section_channels": section_channel_strategy(),
        "skeletal_play_rate": play_rate_strategy(),
        "animation_root_sampling": animation_root_sampling_strategy(),
        "skeletal_completion": "feature_probe",
        "camera_component_resolution": "feature_probe",
        "camera_fov_realization": "component_aware",
    }


def get_section_channels(section: Any) -> list[Any]:
    """Return Sequencer scripting channels across Unreal API variants."""
    get_all = getattr(section, "get_all_channels", None)
    if callable(get_all):
        return list(get_all())

    extensions = getattr(unreal, "MovieSceneSectionExtensions", None)
    extension_get_all = getattr(extensions, "get_all_channels", None) if extensions else None
    if callable(extension_get_all):
        return list(extension_get_all(section))

    legacy = getattr(section, "get_channels", None)
    if callable(legacy):
        return list(legacy())

    raise UnrealCompatibilityError(
        "No supported Sequencer channel API was found. Expected get_all_channels(), "
        "MovieSceneSectionExtensions.get_all_channels(), or legacy get_channels(). "
        f"Unreal runtime: {engine_version()}."
    )


def make_fixed_play_rate(rate: float) -> Any:
    """Create the play-rate representation required by the current Unreal runtime."""
    variant_type = getattr(unreal, "MovieSceneTimeWarpVariant", None)
    if variant_type is None:
        return float(rate)

    variant = variant_type()
    setter = getattr(variant, "set_fixed_play_rate", None)
    if not callable(setter):
        raise UnrealCompatibilityError(
            "MovieSceneTimeWarpVariant exists but set_fixed_play_rate() is unavailable. "
            f"Unreal runtime: {engine_version()}."
        )
    setter(float(rate))
    return variant


def _object_class_name(value: Any) -> str:
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


def _editor_property(value: Any, name: str) -> Any | None:
    getter = getattr(value, "get_editor_property", None)
    if not callable(getter):
        return None
    try:
        return getter(name)
    except Exception:
        return None


def resolve_camera_component(actor: Any) -> tuple[Any, str]:
    """Resolve a camera component without assuming CameraActor/CineCameraActor APIs.

    Unreal exposes different helpers for camera actor families and versions. Prefer
    explicit methods, then reflected editor properties, then component-class discovery.
    """
    for method_name in ("get_cine_camera_component", "get_camera_component"):
        method = getattr(actor, method_name, None)
        if callable(method):
            try:
                component = method()
            except Exception:
                component = None
            if component is not None:
                return component, f"actor.{method_name}"

    component = _editor_property(actor, "camera_component")
    if component is not None:
        return component, "actor.camera_component_property"

    component_getter = getattr(actor, "get_components_by_class", None)
    if callable(component_getter):
        seen: dict[str, Any] = {}
        for class_name in ("CineCameraComponent", "CameraComponent"):
            component_type = getattr(unreal, class_name, None)
            if component_type is None:
                continue
            try:
                candidates = list(component_getter(component_type))
            except Exception:
                continue
            for candidate in candidates:
                path_getter = getattr(candidate, "get_path_name", None)
                key = (
                    str(path_getter())
                    if callable(path_getter)
                    else f"{_object_class_name(candidate)}:{id(candidate)}"
                )
                seen[key] = candidate

        if len(seen) == 1:
            return next(iter(seen.values())), "actor.get_components_by_class"
        if len(seen) > 1:
            raise UnrealCompatibilityError(
                f"Camera actor '{actor.get_actor_label()}' exposes multiple camera components; "
                "the target mapping must identify one unambiguously."
            )

    label_getter = getattr(actor, "get_actor_label", None)
    label = str(label_getter()) if callable(label_getter) else _object_class_name(actor)
    raise UnrealCompatibilityError(
        f"Unable to resolve a camera component for '{label}' "
        f"({_object_class_name(actor)}) on Unreal {engine_version()}. "
        "Tried cine-camera helper, camera helper, reflected camera_component property, "
        "and component-class discovery."
    )


def _set_editor_property(value: Any, name: str, new_value: Any, *, required: bool = True) -> bool:
    setter = getattr(value, "set_editor_property", None)
    if not callable(setter):
        if required:
            raise UnrealCompatibilityError(
                f"{_object_class_name(value)} does not expose set_editor_property()."
            )
        return False
    try:
        setter(name, new_value)
        return True
    except Exception as exc:
        if required:
            raise UnrealCompatibilityError(
                f"Unable to set {_object_class_name(value)}.{name}: {exc}"
            ) from exc
        return False


def _transform_translation_xyz(transform: Any) -> tuple[float, float, float]:
    translation = getattr(transform, "translation", None)
    if translation is None:
        translation = _editor_property(transform, "translation")
    if translation is None:
        raise UnrealCompatibilityError(
            f"{_object_class_name(transform)} does not expose translation."
        )
    return (float(translation.x), float(translation.y), float(translation.z))


def extract_animation_root_delta_cm(
    animation: Any, start_seconds: float, end_seconds: float
) -> tuple[tuple[float, float, float], str]:
    """Inspect the imported target asset's root travel without changing the asset."""
    start = max(0.0, float(start_seconds))
    end = max(start, float(end_seconds))

    library = getattr(unreal, "AnimationLibrary", None)
    length_getter = getattr(library, "get_sequence_length", None) if library else None
    if callable(length_getter):
        try:
            length = float(length_getter(animation))
            if length > 0.0:
                start = min(start, length)
                end = min(end, length)
        except Exception:
            pass

    extract_raw = getattr(library, "extract_root_track_transform", None) if library else None
    if callable(extract_raw):
        try:
            begin = extract_raw(animation, start)
            finish = extract_raw(animation, end)
            bx, by, bz = _transform_translation_xyz(begin)
            ex, ey, ez = _transform_translation_xyz(finish)
            return (ex - bx, ey - by, ez - bz), "AnimationLibrary.extract_root_track_transform"
        except Exception:
            pass

    motion = getattr(unreal, "MotionWarpingUtilities", None)
    extract_motion = (
        getattr(motion, "extract_root_motion_from_animation", None) if motion else None
    )
    if callable(extract_motion):
        try:
            delta = extract_motion(animation, start, end)
            return _transform_translation_xyz(delta), (
                "MotionWarpingUtilities.extract_root_motion_from_animation"
            )
        except Exception:
            pass

    raise UnrealCompatibilityError(
        "Unable to inspect target animation root travel. Expected "
        "AnimationLibrary.extract_root_track_transform() or "
        "MotionWarpingUtilities.extract_root_motion_from_animation(). "
        f"Unreal runtime: {engine_version()}."
    )


def apply_skeletal_root_yaw(section: Any, yaw_degrees: float) -> str:
    """Rotate a skeletal section's root-motion basis without editing the animation asset."""
    rotation = unreal.Rotator(0.0, float(yaw_degrees), 0.0)
    if _set_editor_property(section, "start_rotation_offset", rotation, required=False):
        return "section.start_rotation_offset"
    raise UnrealCompatibilityError(
        "MovieSceneSkeletalAnimationSection does not expose start_rotation_offset; "
        f"cannot align imported root motion on Unreal {engine_version()}."
    )


def set_section_post_roll_frames(section: Any, frames: int) -> str:
    """Hold a section's final evaluated frame for the requested post-roll duration."""
    count = max(0, int(frames))
    setter = getattr(section, "set_post_roll_frames", None)
    if callable(setter):
        try:
            setter(count)
            return "section.set_post_roll_frames"
        except Exception:
            pass

    if _set_editor_property(
        section,
        "post_roll_frames",
        unreal.FrameNumber(count),
        required=False,
    ):
        return "section.post_roll_frames"

    raise UnrealCompatibilityError(
        "MovieScene section does not expose a supported post-roll API; "
        f"cannot hold the final skeletal pose on Unreal {engine_version()}."
    )


def set_section_completion_mode(section: Any, mode: str) -> str:
    """Set post-section state behavior across MovieScene API variants."""
    normalized = str(mode).lower()
    enum_type = getattr(unreal, "MovieSceneCompletionMode", None)
    enum_value = None
    if enum_type is not None:
        if normalized == "keep_state":
            enum_value = getattr(enum_type, "KEEP_STATE", None)
        elif normalized == "restore_state":
            enum_value = getattr(enum_type, "RESTORE_STATE", None)
        elif normalized == "project_default":
            enum_value = getattr(enum_type, "PROJECT_DEFAULT", None)
    if enum_value is None:
        raise UnrealCompatibilityError(f"Unsupported MovieScene completion mode: {mode}")

    setter = getattr(section, "set_completion_mode", None)
    if callable(setter):
        try:
            setter(enum_value)
            return "section.set_completion_mode"
        except Exception:
            pass

    options = _editor_property(section, "eval_options")
    if options is not None and _set_editor_property(
        options, "completion_mode", enum_value, required=False
    ):
        if _set_editor_property(section, "eval_options", options, required=False):
            return "section.eval_options.completion_mode"

    raise UnrealCompatibilityError(
        f"Unable to set MovieScene completion mode '{mode}' on Unreal {engine_version()}."
    )


def _require_positive_fov(value: float) -> float:
    fov = float(value)
    if not 0.0 < fov < 179.0:
        raise UnrealCompatibilityError(f"Unsupported camera FOV value: {fov}")
    return fov


def _vertical_fov_to_focal_length(vertical_fov_degrees: float, sensor_height_mm: float) -> float:
    vertical = math.radians(_require_positive_fov(vertical_fov_degrees))
    if sensor_height_mm <= 0.0:
        raise UnrealCompatibilityError(f"Invalid CineCamera sensor height: {sensor_height_mm}")
    return float(sensor_height_mm) / (2.0 * math.tan(vertical * 0.5))


def _vertical_to_horizontal_fov(vertical_fov_degrees: float, aspect_ratio: float) -> float:
    vertical = math.radians(_require_positive_fov(vertical_fov_degrees))
    if aspect_ratio <= 0.0:
        raise UnrealCompatibilityError(f"Invalid camera aspect ratio: {aspect_ratio}")
    horizontal = 2.0 * math.atan(math.tan(vertical * 0.5) * float(aspect_ratio))
    return math.degrees(horizontal)


def validate_camera_setup(
    component: Any,
    *,
    field_of_view_degrees: float,
    source_axis: str,
    target_aspect: float | None,
    projection: str = "perspective",
) -> dict[str, Any]:
    """Validate target camera semantics without mutating the target."""
    if str(projection).lower() != "perspective":
        raise UnrealCompatibilityError(
            f"Camera projection '{projection}' is not implemented by the Unreal adapter yet."
        )

    normalized_axis = str(source_axis).lower()
    if normalized_axis not in {"vertical", "horizontal"}:
        raise UnrealCompatibilityError(f"Unknown source FOV axis: {source_axis}")
    _require_positive_fov(field_of_view_degrees)

    aspect = float(target_aspect) if target_aspect is not None else None
    if aspect is not None and aspect <= 0.0:
        aspect = None

    setter = getattr(component, "set_editor_property", None)
    if not callable(setter):
        raise UnrealCompatibilityError(
            f"{_object_class_name(component)} does not expose set_editor_property()."
        )

    cine_type = getattr(unreal, "CineCameraComponent", None)
    is_cine = cine_type is not None and isinstance(component, cine_type)
    if is_cine:
        filmback = _editor_property(component, "filmback")
        if filmback is None:
            raise UnrealCompatibilityError(
                "CineCameraComponent does not expose filmback settings required for "
                "source framing preservation."
            )
        sensor_height = _editor_property(filmback, "sensor_height")
        if sensor_height is None:
            sensor_height = getattr(filmback, "sensor_height", None)
        if sensor_height is None or float(sensor_height) <= 0.0:
            raise UnrealCompatibilityError(
                "CineCamera filmback does not expose a valid sensor_height."
            )
        if aspect is not None and not callable(getattr(filmback, "set_editor_property", None)):
            raise UnrealCompatibilityError(
                "CineCamera filmback cannot accept source aspect-ratio settings."
            )
        return {
            "strategy": "cine_filmback_and_focal_length",
            "target_aspect": aspect,
        }

    if aspect is None:
        current_aspect = _editor_property(component, "aspect_ratio")
        if current_aspect is None:
            current_aspect = getattr(component, "aspect_ratio", None)
        if current_aspect is None or float(current_aspect) <= 0.0:
            raise UnrealCompatibilityError(
                "CameraComponent does not expose a valid aspect ratio."
            )
        aspect = float(current_aspect)

    return {
        "strategy": "camera_aspect_and_horizontal_fov",
        "target_aspect": aspect,
    }


def apply_camera_setup(
    component: Any,
    *,
    field_of_view_degrees: float,
    source_axis: str,
    target_aspect: float | None,
    projection: str = "perspective",
) -> dict[str, Any]:
    """Apply non-animated source camera semantics to the target component."""
    if str(projection).lower() != "perspective":
        raise UnrealCompatibilityError(
            f"Camera projection '{projection}' is not implemented by the Unreal adapter yet."
        )

    normalized_axis = str(source_axis).lower()
    if normalized_axis not in {"vertical", "horizontal"}:
        raise UnrealCompatibilityError(f"Unknown source FOV axis: {source_axis}")

    aspect = float(target_aspect) if target_aspect is not None else None
    if aspect is not None and aspect <= 0.0:
        aspect = None

    cine_type = getattr(unreal, "CineCameraComponent", None)
    is_cine = cine_type is not None and isinstance(component, cine_type)

    if is_cine:
        filmback = _editor_property(component, "filmback")
        if filmback is None:
            raise UnrealCompatibilityError(
                "CineCameraComponent does not expose filmback settings required for "
                "source framing preservation."
            )
        sensor_height = _editor_property(filmback, "sensor_height")
        if sensor_height is None:
            sensor_height = getattr(filmback, "sensor_height", None)
        if sensor_height is None or float(sensor_height) <= 0.0:
            raise UnrealCompatibilityError(
                "CineCamera filmback does not expose a valid sensor_height."
            )

        if aspect is not None:
            _set_editor_property(filmback, "sensor_width", float(sensor_height) * aspect)
            _set_editor_property(component, "filmback", filmback)

        if normalized_axis == "vertical":
            focal_length = _vertical_fov_to_focal_length(
                field_of_view_degrees, float(sensor_height)
            )
        else:
            sensor_width = _editor_property(filmback, "sensor_width")
            if sensor_width is None:
                sensor_width = getattr(filmback, "sensor_width", None)
            if sensor_width is None or float(sensor_width) <= 0.0:
                raise UnrealCompatibilityError(
                    "CineCamera filmback does not expose a valid sensor_width."
                )
            horizontal = math.radians(_require_positive_fov(field_of_view_degrees))
            focal_length = float(sensor_width) / (2.0 * math.tan(horizontal * 0.5))

        _set_editor_property(component, "current_focal_length", focal_length)
        _set_editor_property(component, "constrain_aspect_ratio", True, required=False)
        return {
            "strategy": "cine_filmback_and_focal_length",
            "target_aspect": aspect,
            "target_value": focal_length,
            "target_property": "CurrentFocalLength",
        }

    if aspect is None:
        current_aspect = _editor_property(component, "aspect_ratio")
        if current_aspect is None:
            current_aspect = getattr(component, "aspect_ratio", None)
        if current_aspect is None or float(current_aspect) <= 0.0:
            raise UnrealCompatibilityError(
                "CameraComponent does not expose a valid aspect ratio."
            )
        aspect = float(current_aspect)

    _set_editor_property(component, "aspect_ratio", aspect)
    _set_editor_property(component, "constrain_aspect_ratio", True, required=False)

    if normalized_axis == "vertical":
        target_fov = _vertical_to_horizontal_fov(field_of_view_degrees, aspect)
    else:
        target_fov = _require_positive_fov(field_of_view_degrees)
    _set_editor_property(component, "field_of_view", target_fov)
    return {
        "strategy": "camera_aspect_and_horizontal_fov",
        "target_aspect": aspect,
        "target_value": target_fov,
        "target_property": "FieldOfView",
    }


def prepare_camera_fov_track(
    component: Any,
    keys: list[dict[str, Any]],
    source_axis: str,
    target_aspect: float | None = None,
) -> dict[str, Any]:
    """Adapt source animated FOV semantics to the target camera component."""
    normalized_axis = str(source_axis).lower()
    if normalized_axis not in {"vertical", "horizontal"}:
        raise UnrealCompatibilityError(f"Unknown source FOV axis: {source_axis}")

    cine_type = getattr(unreal, "CineCameraComponent", None)
    is_cine = cine_type is not None and isinstance(component, cine_type)

    if is_cine and normalized_axis == "vertical":
        filmback = _editor_property(component, "filmback")
        if filmback is None:
            raise UnrealCompatibilityError(
                "CineCameraComponent does not expose filmback settings required for "
                "vertical-FOV to focal-length conversion."
            )
        sensor_height = _editor_property(filmback, "sensor_height")
        if sensor_height is None:
            sensor_height = getattr(filmback, "sensor_height", None)
        if sensor_height is None:
            raise UnrealCompatibilityError(
                "CineCamera filmback does not expose sensor_height required for FOV conversion."
            )
        converted = [
            {
                "frame": int(key["frame"]),
                "value": _vertical_fov_to_focal_length(float(key["value"]), float(sensor_height)),
            }
            for key in keys
        ]
        return {
            "property_name": "CurrentFocalLength",
            "property_path": "CurrentFocalLength",
            "keys": converted,
            "strategy": "cine_focal_length_from_vertical_fov",
        }

    if normalized_axis == "vertical":
        aspect = float(target_aspect) if target_aspect is not None else None
        if aspect is None or aspect <= 0.0:
            aspect = _editor_property(component, "aspect_ratio")
            if aspect is None:
                aspect = getattr(component, "aspect_ratio", None)
        if aspect is None or float(aspect) <= 0.0:
            raise UnrealCompatibilityError(
                "CameraComponent does not expose aspect_ratio required to convert "
                "source vertical FOV to Unreal horizontal FieldOfView."
            )
        converted = [
            {
                "frame": int(key["frame"]),
                "value": _vertical_to_horizontal_fov(float(key["value"]), float(aspect)),
            }
            for key in keys
        ]
    else:
        converted = [
            {"frame": int(key["frame"]), "value": _require_positive_fov(float(key["value"]))}
            for key in keys
        ]

    return {
        "property_name": "FieldOfView",
        "property_path": "FieldOfView",
        "keys": converted,
        "strategy": "camera_horizontal_fov",
    }


def validate_runtime_capabilities(required_actions: set[str]) -> None:
    """Fail before target mutation when the runtime clearly lacks required feature classes."""
    required_types = {
        "transform": "MovieScene3DTransformTrack",
        "skeletal_animation": "MovieSceneSkeletalAnimationTrack",
        "camera_fov": "MovieSceneFloatTrack",
        "camera_cut": "MovieSceneCameraCutTrack",
        "audio": "MovieSceneAudioTrack",
        "marker": "MovieSceneMarkedFrame",
    }
    missing = [
        required_types[action]
        for action in sorted(required_actions)
        if action in required_types and getattr(unreal, required_types[action], None) is None
    ]
    if missing:
        raise UnrealCompatibilityError(
            "Unreal runtime is missing required CutSceneAI capabilities: "
            + ", ".join(missing)
            + f". Runtime: {engine_version()}."
        )

    if {"transform", "camera_fov"} & required_actions and section_channel_strategy() == "instance_probe":
        # Some older builds only expose the scripting method on section instances. We
        # permit the run and let get_section_channels() perform the definitive probe.
        return
