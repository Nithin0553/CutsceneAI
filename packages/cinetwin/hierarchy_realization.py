"""Plan safe opt-in realization of direct source actor-parent relationships.

No Unreal runtime imports. Actor attachments are allowed only for source
children without their own world-space transform reconstruction track. That
prevents a world-space Sequencer track from double-transforming under a parent.
"""
from __future__ import annotations

from typing import Any

from hierarchy_plan import HierarchyPlanError, plan_actor_hierarchy


class HierarchyRealizationError(ValueError):
    """A direct attachment cannot be reconstructed safely as an Actor hierarchy."""


def build_attachment_operations(
    csir: dict[str, Any],
    mapping: dict[str, Any],
    actions: list[dict[str, Any]],
) -> dict[str, Any]:
    try:
        source = plan_actor_hierarchy(csir, mapping)
    except HierarchyPlanError as exc:
        raise HierarchyRealizationError(str(exc)) from exc

    actor_by_name = {
        entity["name"]: entity for entity in csir.get("entities", [])
    }
    animated_world = {
        action["entity_name"] for action in actions
        if action.get("kind") == "transform"
    }
    corrected_roots = {
        action["entity_name"] for action in actions
        if action.get("kind") == "skeletal_animation"
        and action.get("root_motion_correction_samples")
    }
    edges = source["planned_actor_attachments"]
    for edge in edges:
        if edge["entity_name"] in animated_world | corrected_roots:
            raise HierarchyRealizationError(
                "Cannot automatically attach animated child "
                f"{edge['entity_name']!r}: its world-space transform/root motion "
                "track requires conversion to parent-local space first."
            )

    # The builder currently reconstructs animated transforms in world space.
    # For a moving parent, place it at its *first authored keyed transform*
    # before KEEP_WORLD attachment so the child offset is measured against the
    # same pose Sequencer will evaluate at the beginning.
    first_parent_keys: dict[str, dict[str, Any]] = {}
    for edge in edges:
        parent_name = edge["source_parent_name"]
        candidate_actions = [
            action for action in actions
            if action.get("kind") == "transform"
            and action.get("entity_name") == parent_name
        ]
        if len(candidate_actions) > 1:
            raise HierarchyRealizationError(
                f"Parent {parent_name!r} has multiple independent world-transform "
                "tracks: cannot infer initial attachment basis safely."
            )
        if not candidate_actions:
            continue
        keys = candidate_actions[0].get("keys", [])
        if not keys:
            raise HierarchyRealizationError(
                f"Animated parent {parent_name!r} has no sampled transform keys."
            )
        first = min(keys, key=lambda item: (int(item["frame"]), float(item["time_seconds"])))
        if int(first["frame"]) < 0:
            raise HierarchyRealizationError(
                f"Animated parent {parent_name!r} starts before the playback window."
            )
        if len(first.get("location_cm", [])) != 3 or len(
            first.get("rotation_rpy_degrees", [])
        ) != 3:
            raise HierarchyRealizationError(
                f"Animated parent {parent_name!r} is missing initial pose components."
            )
        first_parent_keys[parent_name] = {
            "actor_label": edge["parent_actor_label"],
            "entity_name": parent_name,
            "first_frame": int(first["frame"]),
            "location_cm": [float(v) for v in first["location_cm"]],
            "rotation_rpy_degrees": [
                float(v) for v in first["rotation_rpy_degrees"]
            ],
            "source_entity_id": actor_by_name[parent_name]["entity_id"],
        }

    # Topologically order mapped source relationships so multi-level actor
    # chains are created with each parent before its mapped children.
    pending = {edge["entity_id"]: dict(edge) for edge in edges}
    ordered: list[dict[str, str]] = []
    while pending:
        ready = [
            edge for edge in pending.values()
            if edge["source_parent_entity_id"] not in pending
        ]
        if not ready:
            raise HierarchyRealizationError(
                "Mapped source attachment graph is cyclic."
            )
        for edge in sorted(ready, key=lambda item: item["entity_name"]):
            ordered.append(edge)
            del pending[edge["entity_id"]]

    return {
        "kind": "cinetwin.actor_attachment_operations",
        "attachments": ordered,
        "parent_initializations": sorted(
            first_parent_keys.values(), key=lambda item: item["entity_name"]
        ),
        "unresolved_source_parents": source["unresolved_source_parents"],
        "policy": "KEEP_WORLD_AT_PARENT_INITIAL_KEY",
        "requires_level_save": bool(ordered),
        "notes": [
            "This plan is read-only; applying it changes the target editor level.",
            "Parent actors with transform tracks are positioned at their first "
            "key before attached children establish KEEP_WORLD offsets.",
            "Unmapped source parents are reported and left unchanged.",
            "Children with their own world-space transform tracks are rejected.",
        ],
    }
