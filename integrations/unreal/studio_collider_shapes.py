"""Stage and observe native shape volumes from an immutable Studio plan."""
from __future__ import annotations

import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import readback_math

_CINETWIN = str(Path(__file__).resolve().parents[2] / "packages" / "cinetwin")
if _CINETWIN not in sys.path:
    sys.path.insert(0, _CINETWIN)

import collider_geometry_compare

ACTION_KIND = "collider_primitive_shape"
ACTIVE_MODE = "world_static_blocking"
_BLOCK_CHANNELS = ("ECC_WORLD_STATIC", "ECC_WORLD_DYNAMIC", "ECC_PHYSICS_BODY")
_SHAPES = {
    "box": ("TriggerBox", "BoxComponent", "set_box_extent", ("get_unscaled_box_extent",)),
    "sphere": ("TriggerSphere", "SphereComponent", "set_sphere_radius",
               ("get_unscaled_sphere_radius",)),
    "capsule": ("TriggerCapsule", "CapsuleComponent", "set_capsule_size",
                ("get_unscaled_capsule_radius", "get_unscaled_capsule_half_height")),
}
_FLOAT32_MAX = 3.402823466e38


class ColliderStagingError(RuntimeError):
    pass


def _active(action: dict[str, Any]) -> bool:
    return action.get("collision_mode") == ACTIVE_MODE


def from_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [action for action in plan.get("actions", []) if action["kind"] == ACTION_KIND]


def _vector(values: Any) -> bool:
    return (isinstance(values, (list, tuple)) and len(values) == 3
            and all(type(value) in (int, float) and math.isfinite(value) for value in values))


def _xyz(value: Any) -> tuple[float, float, float]:
    coords = (float(value.x), float(value.y), float(value.z))
    if not all(math.isfinite(axis) for axis in coords):
        raise ValueError("Nonfinite native collider readback vector.")
    return coords


def preflight(api: Any, actions: list[dict[str, Any]], reserved_labels=()) -> None:
    """Reject missing APIs, malformed native shapes and possible actor reuse."""
    if not actions:
        return
    labels = [action["collider_label"] for action in actions]
    counts = Counter(label.casefold() for label in (*labels, *reserved_labels))
    for action, label in zip(actions, labels):
        spec = _SHAPES.get(action.get("shape"))
        if spec is None or action.get("target_class") != spec[0]:
            raise ColliderStagingError("Unexpected native static collider class.")
        if action.get("collision_mode", "disabled") not in {"disabled", ACTIVE_MODE}:
            raise ColliderStagingError("Unsupported native collider response mode.")
        if _active(action) and (action.get("source_collider_enabled") is not True
                                or action.get("source_is_trigger") is not False
                                or not action.get("actor_label")):
            raise ColliderStagingError("Active collision lacks compatible source intent.")
        if not re.fullmatch(r"CSAI_COLLIDER_[0-9A-F]{20}", label) or counts[label.casefold()] != 1:
            raise ColliderStagingError("Duplicate, occupied or invalid collider label: " + label)
        if not _vector(action.get("location_cm")) or not _vector(action.get("rotation_rpy_degrees")):
            raise ColliderStagingError("Malformed collider transform.")
        if action["shape"] == "box":
            extent = action.get("box_extent_cm")
            dimensions = extent if _vector(extent) else [0]
        elif action["shape"] == "capsule":
            dimensions = [action.get("radius_cm"), action.get("half_height_cm")]
        else:
            dimensions = [action.get("radius_cm")]
        if any(type(value) not in (int, float) or not 0 < value <= _FLOAT32_MAX
               for value in dimensions):
            raise ColliderStagingError("Malformed collider dimensions.")
        if action["shape"] == "capsule" and dimensions[1] < dimensions[0]:
            raise ColliderStagingError("Capsule half-height is smaller than its radius.")
        actor_class, component_class = (getattr(api, name, None) for name in spec[:2])
        if actor_class is None or component_class is None:
            raise ColliderStagingError("Unreal static collider class unavailable: " + spec[0])
        required = (
            spec[2], *spec[3], "set_collision_enabled", "get_collision_enabled",
            "set_collision_profile_name", "get_collision_profile_name",
            "get_editor_property", "set_editor_property",
        )
        if _active(action):
            required += ("set_collision_object_type", "get_collision_object_type",
                         "set_collision_response_to_all_channels", "set_collision_response_to_channel",
                         "get_collision_response_to_channel")
            tokens = (
                ("CollisionEnabled", "QUERY_AND_PHYSICS"),
                ("CollisionResponseType", "ECR_BLOCK"), ("CollisionResponseType", "ECR_IGNORE"),
                *(("CollisionChannel", name) for name in (*_BLOCK_CHANNELS, "ECC_CAMERA")),
            )
            if any(getattr(getattr(api, group, None), attr, None) is None for group, attr in tokens):
                raise ColliderStagingError("Unreal static blocking collision API unavailable.")
        if any(not callable(getattr(component_class, member, None)) for member in required):
            raise ColliderStagingError("Unreal native collider component API unavailable: " + spec[1])
    if getattr(getattr(api, "CollisionEnabled", None), "NO_COLLISION", None) is None:
        raise ColliderStagingError("Unreal cannot disable native shape collisions.")
    editor_type = getattr(api, "EditorActorSubsystem", None)
    if any(not callable(getattr(editor_type, method, None))
           for method in ("spawn_actor_from_class", "destroy_actor", "get_all_level_actors")):
        raise ColliderStagingError("Unreal editor shape staging API unavailable.")


def _component(api: Any, actor: Any, action: dict[str, Any]) -> Any:
    spec = _SHAPES[action["shape"]]
    if str(actor.get_class().get_name()) != spec[0]:
        raise ColliderStagingError("Native volume class differs from the planned class.")
    found = actor.get_components_by_class(getattr(api, spec[1]))
    if len(found) != 1 or found[0] != actor.get_editor_property("root_component"):
        raise ColliderStagingError("Expected one native shape as the volume root component.")
    return found[0]


def _read_queries(api: Any, action: dict[str, Any], actor: Any, component: Any,
                  actors: list[Any]) -> dict[str, Any]:
    source = action.get("source_collider_probes") or []
    if not source:
        return {**collider_geometry_compare.compare_rays([], []),
                "reason": "UNITY_NATIVE_RAYS_MISSING"}
    target = []
    try:
        query_type = api.ObjectTypeQuery.OBJECT_TYPE_QUERY1
        ignored = [other for other in actors if other != actor]
        for ray in source:
            result = api.SystemLibrary.line_trace_single_for_objects(
                actor, api.Vector(*ray["start_cm"]), api.Vector(*ray["end_cm"]),
                [query_type], False, ignored, api.DrawDebugTrace.NONE, False,
            )
            if result is None:
                target.append({"hit": False, "distance_m": None})
                continue
            if result.hit_actor != actor or result.hit_component != component:
                raise ColliderStagingError("Native trace did not identify the planned collider.")
            distance = float(result.distance) / 100
            if not math.isfinite(distance) or distance < 0:
                raise ColliderStagingError("Native trace reported an invalid distance.")
            target.append({"hit": True, "distance_m": distance})
    except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
        return {**collider_geometry_compare.compare_rays(source, []), "reason": str(exc)}
    return collider_geometry_compare.compare_rays(source, target)


def inspect(api: Any, actions: list[dict[str, Any]], actors: list[Any], *,
            measure_queries: bool = False) -> list[dict[str, Any]]:
    """Measure actual shapes directly from the loaded level, including after reopen."""
    if not actions:
        return []
    by_label: dict[str, list[Any]] = {}
    for actor in actors:
        by_label.setdefault(str(actor.get_actor_label()), []).append(actor)
    results = []
    for action in actions:
        label, shape = action["collider_label"], action["shape"]
        item = {
            "source_component_id": action["source_component_id"], "actor_label": label,
            "adapter_name": action["adapter_name"], "shape": shape, "status": "INCOMPLETE",
            "source_collider_enabled": action["source_collider_enabled"],
            "source_is_trigger": action["source_is_trigger"], "behavior_verified": False,
            "collision_mode": action.get("collision_mode", "disabled"),
            "interaction_limitation": action.get("interaction_limitation"),
        }
        results.append(item)
        matches = by_label.get(label, [])
        if len(matches) != 1:
            item.update(status="FAIL", reason="EXPECTED_ONE_NATIVE_COLLIDER_VOLUME")
            continue
        actor = matches[0]
        try:
            component = _component(api, actor, action)
            rotation = actor.get_actor_rotation()
            canonical = readback_math.target_transform_to_canonical(
                _xyz(actor.get_actor_location()), (rotation.roll, rotation.pitch, rotation.yaw),
                _xyz(actor.get_actor_scale3d()),
            )
            observed = {"center_m": canonical["position_m"],
                        "rotation_xyzw": canonical["rotation_xyzw"]}
            if shape == "box":
                x, y, z = _xyz(component.get_unscaled_box_extent())
                observed["size_m"] = [y / 50, z / 50, x / 50]
            elif shape == "sphere":
                observed["radius_m"] = float(component.get_unscaled_sphere_radius()) / 100
            else:
                observed["radius_m"] = float(component.get_unscaled_capsule_radius()) / 100
                observed["height_m"] = float(component.get_unscaled_capsule_half_height()) / 50
            comparison = collider_geometry_compare.compare(shape, action["source_geometry"], observed)
            collision_disabled = (
                not actor.get_actor_enable_collision()
                and component.get_editor_property("generate_overlap_events") is False
                and str(component.get_collision_profile_name()) == "NoCollision"
                and component.get_collision_enabled() == api.CollisionEnabled.NO_COLLISION
            )
            mode_matches = collision_disabled
            if _active(action):
                response = api.CollisionResponseType
                channels = api.CollisionChannel
                owners = by_label.get(action["actor_label"], [])
                mode_matches = (
                    len(owners) == 1 and not owners[0].get_actor_enable_collision()
                    and actor.get_actor_enable_collision()
                    and component.get_editor_property("generate_overlap_events") is False
                    and component.get_collision_enabled() == api.CollisionEnabled.QUERY_AND_PHYSICS
                    and component.get_collision_object_type() == channels.ECC_WORLD_STATIC
                    and all(component.get_collision_response_to_channel(getattr(channels, key))
                            == response.ECR_BLOCK for key in _BLOCK_CHANNELS)
                    and component.get_collision_response_to_channel(channels.ECC_CAMERA)
                    == response.ECR_IGNORE
                )
                if measure_queries:
                    item["query_comparison"] = _read_queries(api, action, actor, component, actors)
            has_unit_scale = all(math.isclose(v, 1.0, abs_tol=1e-6, rel_tol=0)
                                 for v in canonical["scale_xyz"])
            detached = actor.get_attach_parent_actor() is None
            item.update(
                source_geometry=action["source_geometry"], observed_geometry=observed,
                geometry_comparison=comparison, collision_disabled=collision_disabled,
                collision_mode_matches=bool(mode_matches),
                unit_scale=has_unit_scale, detached=detached,
                status=("PASS" if comparison["status"] == "PASS" and mode_matches
                        and has_unit_scale and detached else "FAIL"),
            )
        except ColliderStagingError as exc:
            item.update(status="FAIL", reason=str(exc))
        except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
            item["reason"] = str(exc)
    return results


def stage(api: Any, editor: Any, actions: list[dict[str, Any]], operations: list[dict[str, Any]],
          *, owned_actors: dict[str, Any] | None = None) -> None:
    """Only edit newly spawned volumes and clean up those volumes on error."""
    if not actions:
        return
    preflight(api, actions, (str(actor.get_actor_label()) for actor in editor.get_all_level_actors()))
    spawned = []
    owned_actors = owned_actors or {}
    active_owner_labels = {action["actor_label"] for action in actions if _active(action)}
    if not active_owner_labels.issubset(owned_actors):
        raise ColliderStagingError("Active collision requires freshly staged source owner actors.")
    owner_flags = [
        (owned_actors[label], owned_actors[label].get_actor_enable_collision())
        for label in sorted(active_owner_labels)
    ]
    try:
        # Replace importer defaults on the created render actors for these
        # exact Unity owners to avoid duplicate blocking volume/mesh collision.
        for owner, _ in owner_flags:
            owner.set_actor_enable_collision(False)
        for action in actions:
            operation = {
                "source_component_id": action["source_component_id"],
                "adapter_name": action["adapter_name"], "label": action["collider_label"],
                "status": "SPAWN_STARTED", "collision_mode": action.get("collision_mode", "disabled"),
            }
            operations.append(operation)
            roll, pitch, yaw = action["rotation_rpy_degrees"]
            actor = editor.spawn_actor_from_class(
                getattr(api, action["target_class"]), api.Vector(*action["location_cm"]),
                api.Rotator(roll=roll, pitch=pitch, yaw=yaw),
            )
            if actor is None:
                raise ColliderStagingError("Unreal could not spawn " + action["collider_label"])
            spawned.append((actor, operation))
            actor.set_actor_label(action["collider_label"], mark_dirty=True)
            actor.set_actor_enable_collision(False)
            component = _component(api, actor, action)
            component.set_editor_property("generate_overlap_events", False)
            component.set_collision_profile_name("NoCollision", False)
            component.set_collision_enabled(api.CollisionEnabled.NO_COLLISION)
            shape = action["shape"]
            if shape == "box":
                component.set_box_extent(api.Vector(*action["box_extent_cm"]), False)
            elif shape == "sphere":
                component.set_sphere_radius(action["radius_cm"], False)
            else:
                component.set_capsule_size(action["radius_cm"], action["half_height_cm"], False)
            if _active(action):
                channels = api.CollisionChannel
                response = api.CollisionResponseType
                component.set_collision_profile_name("Custom", False)
                component.set_collision_object_type(channels.ECC_WORLD_STATIC)
                component.set_collision_response_to_all_channels(response.ECR_IGNORE)
                for key in _BLOCK_CHANNELS:
                    component.set_collision_response_to_channel(getattr(channels, key), response.ECR_BLOCK)
                component.set_collision_enabled(api.CollisionEnabled.QUERY_AND_PHYSICS)
                actor.set_actor_enable_collision(True)
        readback = inspect(api, actions, editor.get_all_level_actors())
        for operation, row in zip(operations, readback):
            operation["readback"] = row
        if any(row["status"] != "PASS" for row in readback):
            raise ColliderStagingError("Native collider geometry readback failed before saving.")
        for operation in operations:
            operation["status"] = "CREATED_IN_MEMORY_GEOMETRY_READ_BACK"
    except Exception:
        for actor, operation in reversed(spawned):
            try:
                removed = editor.destroy_actor(actor)
            except Exception:
                removed = False
            operation["status"] = "ROLLED_BACK" if removed else "ROLLBACK_REVIEW_REQUIRED"
        for owner, enabled in owner_flags:
            try:
                owner.set_actor_enable_collision(enabled)
            except Exception:
                operations.append({"status": "ROLLBACK_REVIEW_REQUIRED",
                                   "label": str(owner.get_actor_label())})
        raise
