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


def runtime_profile() -> dict[str, str]:
    """Return a compact capability profile for logging and provenance."""
    return {
        "engine_version": engine_version(),
        "section_channels": section_channel_strategy(),
        "skeletal_play_rate": play_rate_strategy(),
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


def prepare_camera_fov_track(
    component: Any, keys: list[dict[str, Any]], source_axis: str
) -> dict[str, Any]:
    """Adapt source FOV semantics to the target camera component.

    Unity Camera.fieldOfView is vertical.  CineCamera components are realized through
    focal length using their filmback sensor height; generic CameraComponents use their
    horizontal FieldOfView after aspect-ratio conversion.
    """
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
        aspect = _editor_property(component, "aspect_ratio")
        if aspect is None:
            aspect = getattr(component, "aspect_ratio", None)
        if aspect is None:
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
