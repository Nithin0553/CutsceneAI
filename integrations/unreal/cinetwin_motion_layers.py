"""Read-only Unreal actor, SceneComponent, and attachment observations.

Records actual world-space transformations of each motion carrier independently
after a tick-synchronized Sequencer seek. Never modifies evaluated scene state.
"""
from __future__ import annotations

from typing import Any

import unreal

import readback_math


class MotionLayerObservationError(RuntimeError):
    pass


def _component_transform(component: Any) -> dict[str, list[float]]:
    loc = component.get_world_location()
    rot = component.get_world_rotation()
    scale = component.get_world_scale()
    return readback_math.target_transform_to_canonical(
        (float(loc.x), float(loc.y), float(loc.z)),
        (float(rot.roll), float(rot.pitch), float(rot.yaw)),
        (float(scale.x), float(scale.y), float(scale.z)),
    )


def observe_actor_motion_layers(actor: Any, entity_id: str) -> dict[str, Any]:
    """Capture all SceneComponents, the actor's attachment, and world transforms.

    Component names can repeat; their full object paths provide unique
    identities within a single run. Object paths should not be treated as
    durable IDs across project transfers.
    """
    parent_actor = actor.get_attach_parent_actor()
    components = list(actor.get_components_by_class(unreal.SceneComponent))
    if len(components) > 128:
        raise MotionLayerObservationError(
            "Unexpectedly many scene components on actor "
            + str(actor.get_actor_label())
        )
    observed = []
    seen_paths: set[str] = set()
    for component in components:
        path = str(component.get_path_name())
        if not path or path in seen_paths:
            raise MotionLayerObservationError(
                "Missing or repeated SceneComponent path on actor "
                + str(actor.get_actor_label())
            )
        seen_paths.add(path)
        parent_component = component.get_attach_parent()
        parent_owner = parent_component.get_owner() if parent_component else None
        observed.append({
            "component_path": path,
            "component_name": str(component.get_name()),
            "component_class": str(component.get_class().get_name()),
            "parent_component_path": (
                str(parent_component.get_path_name())
                if parent_component is not None else None
            ),
            "parent_actor_label": (
                str(parent_owner.get_actor_label())
                if parent_owner is not None else None
            ),
            "world_transform": _component_transform(component),
        })
    return {
        "entity_id": entity_id,
        "actor_label": str(actor.get_actor_label()),
        "attached_to_actor_label": (
            str(parent_actor.get_actor_label()) if parent_actor is not None else None
        ),
        "attached_to_socket": (
            str(actor.get_attach_parent_socket_name())
            if parent_actor is not None else None
        ),
        "components": sorted(observed, key=lambda entry: entry["component_path"]),
    }
