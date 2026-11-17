"""Source-backed native geometry for authored static Unity collider primitives."""
from __future__ import annotations

import hashlib
import math
from functools import partial
from typing import Any

import csir_plan
import feature_dispatch
import source_surface_gap

ACTION_KIND = "collider_primitive_shape"
STRATEGY = "static_authoring_geometry_snapshot"
LOSSES = (
    "Unity physics layers and query filtering", "contacts, triggers and callbacks",
    "physics materials and simulation", "runtime enablement and motion",
)
ACTIVE_MODE = "world_static_blocking"
ACTIVE_LOSSES = (
    "Nondefault Unity layers and per-pair runtime filtering", "contact solver, callbacks and triggers",
    "physics material and simulated state", "runtime enablement and motion",
)


def _ray_point(row):
    if not isinstance(row, dict):
        return None
    values = [row.get(axis) for axis in "xyz"]
    if not all(type(value) in (float, int) and abs(value) <= 1e7 for value in values):
        return None
    x, y, z = values
    return list(csir_plan.canonical_position_to_unreal_cm((x, y, -z)))


def _interaction(source):
    record = source.get("collider_interaction")
    if not isinstance(record, dict) or record.get("version") != "1.0.0":
        return "disabled", "COLLIDER_INTERACTION_CAPTURE_REQUIRED", []
    if not source["enabled"] or source["is_trigger"]:
        return "disabled", "SOURCE_COLLIDER_DISABLED_OR_TRIGGER", []
    if (any(type(record.get(field)) is not int or record[field] != 0
            for field in ("layer", "include_layers", "exclude_layers"))
            or record.get("default_layer_contacts") is not True
            or record.get("has_authored_physics_material") is not False
            or type(record.get("owner_collider_count")) is not int
            or record["owner_collider_count"] != 1):
        return "disabled", "SOURCE_COLLISION_FILTER_OR_MATERIAL_UNSUPPORTED", []
    rays = record.get("rays")
    if not isinstance(rays, list) or len(rays) != 4:
        return ACTIVE_MODE, None, []
    probes = []
    for ray in rays:
        if not isinstance(ray, dict) or type(ray.get("hit")) is not bool:
            return ACTIVE_MODE, None, []
        start, end = _ray_point(ray.get("start_m")), _ray_point(ray.get("end_m"))
        distance = ray.get("distance_m")
        if (start is None or end is None or start == end
                or type(distance) not in (float, int)
                or not 0 <= distance <= math.dist(start, end) / 100 + 1e-5
                or (not ray["hit"] and distance != 0)):
            return ACTIVE_MODE, None, []
        probes.append({"start_cm": start, "end_cm": end,
                       "hit": ray["hit"], "distance_m": distance if ray["hit"] else None})
    # A native source capture with only misses does not establish a valid body.
    if [probe["hit"] for probe in probes] != [True, True, True, False]:
        probes = []
    return ACTIVE_MODE, None, probes


def _require_static_scope(csir, entity_id):
    entities = {entity["entity_id"]: entity for entity in csir["entities"]}
    lineage = set()
    while entity_id:
        if entity_id in lineage or entity_id not in entities:
            raise feature_dispatch.ComponentEvidenceError("SOURCE_COLLIDER_ANCESTRY_UNRESOLVED")
        lineage.add(entity_id)
        entity_id = entities[entity_id].get("parent_entity_id")
    if any(track.get("muted") is not True and track.get("binding_entity_id") in lineage
           for track in csir.get("tracks", [])):
        raise feature_dispatch.ComponentEvidenceError("TIMELINE_BOUND_COLLIDER_NEEDS_MOTION_ADAPTER")


def _convert(csir, mapping, row, target, *, target_class) -> dict[str, Any]:
    if not source_surface_gap.source_capture_valid(row):
        raise feature_dispatch.ComponentEvidenceError("SOURCE_COLLIDER_GEOMETRY_INVALID")
    source = row["feature"]
    if (source["primitive_snapshot_version"] != "1.0.0"
            or source["primitive_transform_supported"] is not True):
        raise feature_dispatch.ComponentEvidenceError("COLLIDER_TRANSFORM_OR_SNAPSHOT_UNSUPPORTED")
    if source["collider_has_body"] is not False or source["collider_owner_static"] is not True:
        raise feature_dispatch.ComponentEvidenceError("DYNAMIC_COLLIDER_NEEDS_SIMULATION_ADAPTER")
    if source["collider_owner_active"] is not True:
        raise feature_dispatch.ComponentEvidenceError("INACTIVE_COLLIDER_OWNER")
    if mapping.get("enable_native_component_staging") is not True:
        raise feature_dispatch.ComponentEvidenceError("AUTOMATIC_SCENE_STAGING_REQUIRED")
    _require_static_scope(csir, target["entity_id"])

    center_xyz = source["world_center_m"]
    center = (center_xyz["x"], center_xyz["y"], -center_xyz["z"])
    rotation = source["world_rotation_xyzw"]
    quat = (-rotation["x"], -rotation["y"], rotation["z"], rotation["w"])
    if not math.isclose(math.hypot(*quat), 1, abs_tol=1e-5, rel_tol=0):
        raise feature_dispatch.ComponentEvidenceError("SOURCE_COLLIDER_ROTATION_NOT_UNIT")
    shape = source["shape"]
    source_geometry = {"center_m": list(center), "rotation_xyzw": list(quat)}
    native_geometry = {}
    if shape == "box":
        size = source["world_size_m"]
        source_geometry["size_m"] = [size[axis] for axis in "xyz"]
        native_geometry["box_extent_cm"] = [size[axis] * 50 for axis in "zxy"]
    else:
        source_geometry["radius_m"] = source["world_radius_m"]
        native_geometry["radius_cm"] = source["world_radius_m"] * 100
        if shape == "capsule":
            source_geometry["height_m"] = source["world_height_m"]
            native_geometry["half_height_cm"] = source["world_height_m"] * 50

    label_digest = hashlib.sha256(
        (mapping["sequence_asset_path"] + "\0" + row["component_global_id"]).encode("utf-8")
    ).hexdigest()[:20].upper()
    mode, limitation, probes = _interaction(source)
    return {
        "kind": ACTION_KIND, "target_class": target_class,
        "entity_name": target["name"], "actor_label": target["actor_label"],
        "collider_label": "CSAI_COLLIDER_" + label_digest, "shape": shape,
        "location_cm": list(csir_plan.canonical_position_to_unreal_cm(center)),
        "rotation_rpy_degrees": list(csir_plan.canonical_quat_to_unreal_rotator(quat)),
        "source_geometry": source_geometry, **native_geometry,
        "source_collider_enabled": source["enabled"], "source_is_trigger": source["is_trigger"],
        "collision_mode": mode, "interaction_limitation": limitation,
        "source_collider_probes": probes,
        "source_semantic": "physics.collider", "source_behavior_strategy": STRATEGY,
        "fidelity_status": "STATIC_COLLIDER_GEOMETRY_AND_BEHAVIOR_UNVERIFIED",
        "semantic_losses": list(ACTIVE_LOSSES if mode == ACTIVE_MODE else LOSSES),
    }


def install(registry: feature_dispatch.HandlerRegistry) -> None:
    for shape, component, target_class in (
        ("box", "BoxCollider", "TriggerBox"),
        ("sphere", "SphereCollider", "TriggerSphere"),
        ("capsule", "CapsuleCollider", "TriggerCapsule"),
    ):
        registry.register_component(feature_dispatch.ComponentAdapter(
            adapter_id="unity_static_" + shape + "_collider", version="1.1.0",
            source_type="UnityEngine." + component, source_assembly="UnityEngine.PhysicsModule",
            semantic="physics.collider",
            source_versions=("2022.3", "6000.0", "6000.1", "6000.2", "6000.3"),
            target_versions=("5.8",), target_classes=(target_class,), action_kind=ACTION_KIND,
            strategy=STRATEGY,
            required_fields=("primitive_snapshot_version", "primitive_transform_supported",
                             "collider_owner_static", "collider_has_body", "collider_owner_active"),
            dependency_fields=(),
            preflight="Fresh staging map, unique generated volume label and native shape API.",
            readback="Native volume shape, dimensions, world pose and collision mode.",
            behavior="Compare native hit, miss and distance for eligible static blockers.",
            unsupported_properties=LOSSES, planner=partial(_convert, target_class=target_class),
        ))
