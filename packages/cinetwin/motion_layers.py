"""Analyze motion carriers and attachment evidence without engine imports.

Pure-Python diagnostics. Distinguish actor motion, animated SceneComponents,
skeletal root-bone motion, and parent relationships. No cross-rig retargeting
or automatic correctness verdict is implied.
"""
from __future__ import annotations

import math
from typing import Any


class MotionLayerEvidenceError(ValueError):
    pass


def _point(values: Any, name: str) -> tuple[float, float, float]:
    if not isinstance(values, list) or len(values) != 3:
        raise MotionLayerEvidenceError(f"{name}: expected three coordinates.")
    try:
        xyz = tuple(float(v) for v in values)
    except (TypeError, ValueError) as exc:
        raise MotionLayerEvidenceError(f"{name}: nonnumeric coordinates.") from exc
    if any(not math.isfinite(v) for v in xyz):
        raise MotionLayerEvidenceError(f"{name}: nonfinite coordinates.")
    return xyz  # type: ignore[return-value]


def _travel_cm(points: list[tuple[float, float, float]]) -> float:
    return round(max(math.dist(points[0], p) for p in points) * 100.0, 5)


def analyze_motion_layers(
    plan: dict[str, Any],
    samples: list[dict[str, Any]],
    native_rigs: list[dict[str, Any]],
    *,
    static_tolerance_cm: float = 0.1,
) -> list[dict[str, Any]]:
    if not samples:
        raise MotionLayerEvidenceError("No observed samples.")
    if len(samples) < 2:
        raise MotionLayerEvidenceError("Need at least two time-aligned samples.")
    if not 0 < static_tolerance_cm < 10:
        raise MotionLayerEvidenceError("Static tolerance must be between 0 and 10cm.")

    bound = {}
    first_layers = samples[0].get("motion_layers")
    if not isinstance(first_layers, list):
        raise MotionLayerEvidenceError("Missing target motion_layers observations.")
    for row in first_layers:
        eid = row.get("entity_id")
        if not isinstance(eid, str) or not eid or eid in bound:
            raise MotionLayerEvidenceError("Duplicate or absent motion layer entity ID.")
        bound[eid] = row["actor_label"]

    source_parent = {
        entity["entity_id"]: entity.get("parent_entity_id")
        for entity in plan.get("entities", [])
    }
    rig_roots = {}
    for rig in native_rigs:
        rig_id = rig["entity_id"]
        roots = [
            bone["bone_name"] for bone in rig.get("native_target_bones", [])
            if not bone.get("parent_bone_name")
        ]
        if not roots:
            raise MotionLayerEvidenceError(f"Rig {rig_id} has no root bone.")
        rig_roots[rig_id] = set(roots)
    results = []
    for eid, actor_label in bound.items():
        actor_xyz = []
        component_paths = None
        component_positions: dict[str, list[tuple[float, float, float]]] = {}
        parents = []
        root_positions: dict[str, list[tuple[float, float, float]]] = {
            name: [] for name in rig_roots.get(eid, [])
        }
        for idx, frame in enumerate(samples):
            entities = [
                entry for entry in frame.get("entities", [])
                if entry.get("entity_id") == eid
            ]
            layers = [
                entry for entry in frame.get("motion_layers", [])
                if entry.get("entity_id") == eid
            ]
            if len(entities) != 1 or len(layers) != 1:
                raise MotionLayerEvidenceError(
                    f"Sample {idx} missing/repeated actor {eid}."
                )
            if entities[0].get("actor_label") != actor_label:
                raise MotionLayerEvidenceError(f"Actor label changed for {eid}.")
            row = layers[0]
            if row.get("actor_label") != actor_label:
                raise MotionLayerEvidenceError(f"Motion layer actor label changed: {eid}.")
            actor_xyz.append(
                _point(entities[0]["world_transform"]["position_m"], "actor position")
            )
            parents.append(row.get("attached_to_actor_label"))
            components = row.get("components", [])
            current = {}
            for component in components:
                path = component.get("component_path")
                if not isinstance(path, str) or not path or path in current:
                    raise MotionLayerEvidenceError(
                        f"Sample {idx} duplicate SceneComponent for {eid}."
                    )
                current[path] = _point(
                    component["world_transform"]["position_m"],
                    f"component {path} position",
                )
            if component_paths is None:
                component_paths = set(current)
                component_positions = {path: [] for path in component_paths}
            if set(current) != component_paths:
                raise MotionLayerEvidenceError(
                    f"Sample {idx} component topology changed for {eid}."
                )
            for path, coords in current.items():
                component_positions[path].append(coords)
            if eid in rig_roots:
                poses = [
                    entry for entry in frame.get("skeletal_poses", [])
                    if entry.get("entity_id") == eid
                ]
                if len(poses) != 1:
                    raise MotionLayerEvidenceError(
                        f"Sample {idx} skeletal rig missing/repeated: {eid}."
                    )
                roots = [
                    bone for bone in poses[0]["bones"]
                    if bone.get("bone_name") in rig_roots[eid]
                ]
                if {bone["bone_name"] for bone in roots} != rig_roots[eid]:
                    raise MotionLayerEvidenceError(
                        f"Sample {idx} missing root bones: {eid}."
                    )
                for bone in roots:
                    root_positions[bone["bone_name"]].append(
                        _point(bone["world_position_m"], "root bone position")
                    )

        expected_parent_id = source_parent.get(eid)
        expected_parent_actor = bound.get(expected_parent_id)
        unique_parents = sorted(set(str(p) for p in parents))
        if expected_parent_actor is None:
            relationship_status = (
                "SOURCE_PARENT_NOT_MAPPED" if expected_parent_id
                else "NO_SOURCE_PARENT"
            )
        elif any(parent != expected_parent_actor for parent in parents):
            relationship_status = "ACTOR_ATTACHMENT_DIFFERS_FROM_SOURCE"
        else:
            relationship_status = "ACTOR_ATTACHMENT_MATCH"
        actor_motion = _travel_cm(actor_xyz)
        component_motion = {
            path: _travel_cm(coords) for path, coords in component_positions.items()
        }
        root_motion = {
            name: _travel_cm(coords) for name, coords in root_positions.items()
        }
        max_component = max(component_motion.values(), default=0.0)
        max_root = max(root_motion.values(), default=0.0)
        if actor_motion > static_tolerance_cm:
            carrier = "ACTOR_TRANSFORM_MOVES"
        elif max_component > static_tolerance_cm:
            carrier = "COMPONENT_MOVES_ACTOR_STATIC"
        elif max_root > static_tolerance_cm:
            carrier = "SKELETAL_ROOT_MOVES_ACTOR_STATIC"
        else:
            carrier = "NO_TRANSLATION_OBSERVED_ON_ACTOR_COMPONENT_OR_ROOT_BONE"

        results.append({
            "entity_id": eid,
            "actor_label": actor_label,
            "source_parent_entity_id": expected_parent_id,
            "source_parent_target_actor_label": expected_parent_actor,
            "observed_attachment_parent_labels": unique_parents,
            "attachment_diagnostic": relationship_status,
            "actor_motion_cm": actor_motion,
            "max_component_motion_cm": max_component,
            "component_motion_cm": component_motion,
            "skeletal_root_bone_motion_cm": root_motion,
            "motion_carrier_diagnostic": carrier,
            "sample_count": len(samples),
        })
    return sorted(results, key=lambda item: item["actor_label"])
