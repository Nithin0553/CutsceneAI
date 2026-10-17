"""Apply opt-in, preflighted CineTwin actor attachments in Unreal Editor.

Existing foreign attachments are never overwritten. The plan includes only
directly mapped source actor-parent links that have no child world-space track.
This module never saves the level; the caller must preserve the editor level
before making such changes persistent.
"""
from __future__ import annotations

from typing import Any

import unreal

import unreal_compat


class UnrealHierarchyError(RuntimeError):
    pass


def _actor_lookup() -> dict[str, Any]:
    actors = unreal.get_editor_subsystem(
        unreal.EditorActorSubsystem
    ).get_all_level_actors()
    results: dict[str, Any] = {}
    duplicated: set[str] = set()
    for actor in actors:
        name = str(actor.get_actor_label())
        if name in results:
            duplicated.add(name)
        else:
            results[name] = actor
    for name in duplicated:
        results.pop(name, None)
    return results


def _restore_transform(actor: Any, saved: Any) -> None:
    actor.set_actor_transform(saved, False, True)


def _detach_keep_world(actor: Any) -> None:
    rule = unreal.DetachmentRule.KEEP_WORLD
    actor.detach_from_actor(rule, rule, rule)


def rollback_hierarchy(change_log: list[dict[str, Any]]) -> None:
    """Undo only attachments and parent initializations applied this run."""
    errors = []
    for change in reversed(change_log):
        try:
            if change["kind"] == "new_attachment":
                _detach_keep_world(change["child"])
                _restore_transform(change["child"], change["previous_world_transform"])
            elif change["kind"] == "parent_initialization":
                _restore_transform(change["parent"], change["previous_world_transform"])
        except Exception as exc:
            errors.append(str(exc))
    if errors:
        raise UnrealHierarchyError(
            "Hierarchy rollback incomplete: " + "; ".join(errors)
        )


def apply_hierarchy(
    operations: dict[str, Any],
) -> list[dict[str, Any]]:
    """Apply directly mapped actor attachments after strict non-mutating preflight.

    Returns a change log suitable for rollback if later sequence construction
    fails. Callers must not assume this saves changes to the Unreal level.
    """
    edges = operations.get("attachments", [])
    if not edges:
        return []

    unreal.AttachmentRule.KEEP_WORLD
    unreal.DetachmentRule.KEEP_WORLD
    actors = _actor_lookup()
    needed = {
        entry["actor_label"] for entry in edges
    } | {
        entry["parent_actor_label"] for entry in edges
    }
    missing = sorted(needed - actors.keys())
    if missing:
        raise UnrealHierarchyError(
            "Hierarchy realization requires unique level actors: "
            + ", ".join(missing)
        )

    pending: list[dict[str, Any]] = []
    new_parent_labels: set[str] = set()
    for edge in edges:
        child = actors[edge["actor_label"]]
        parent = actors[edge["parent_actor_label"]]
        if child == parent:
            raise UnrealHierarchyError("Cannot attach actor to itself.")
        old_parent = child.get_attach_parent_actor()
        if old_parent is parent:
            unreal.log(
                "[CineTwin] Existing parent link already correct: "
                + edge["actor_label"] + " -> " + edge["parent_actor_label"]
            )
            continue
        if old_parent is not None:
            raise UnrealHierarchyError(
                "Refusing to replace unrelated existing attachment for "
                f"{edge['actor_label']}: "
                f"current={old_parent.get_actor_label()}, "
                f"expected={edge['parent_actor_label']}"
            )
        if edge.get("attachment_rule") != "KEEP_WORLD" or edge.get("socket"):
            raise UnrealHierarchyError(
                "Only source-aligned root-to-root KEEP_WORLD attachments are supported."
            )
        pending.append(edge)
        new_parent_labels.add(edge["parent_actor_label"])

    # Preflight complete before any transform/attachment operation.
    initialization = [
        value for value in operations.get("parent_initializations", [])
        if value["actor_label"] in new_parent_labels
    ]
    for value in initialization:
        if value["actor_label"] not in actors:
            raise UnrealHierarchyError(
                "Cannot initialize missing animated source parent actor."
            )
        if len(value["location_cm"]) != 3 or len(
            value["rotation_rpy_degrees"]
        ) != 3:
            raise UnrealHierarchyError("Invalid initial parent transform key.")

    changes: list[dict[str, Any]] = []
    try:
        for initial in initialization:
            parent = actors[initial["actor_label"]]
            changes.append({
                "kind": "parent_initialization",
                "parent": parent,
                "previous_world_transform": parent.get_actor_transform(),
            })
            x, y, z = initial["location_cm"]
            roll, pitch, yaw = initial["rotation_rpy_degrees"]
            parent.set_actor_location(unreal.Vector(x, y, z), False, True)
            parent.set_actor_rotation(
                unreal_compat.make_rotator_semantic(
                    roll=roll, pitch=pitch, yaw=yaw
                ),
                True,
            )
            unreal.log(
                "[CineTwin] Initialized animated attachment parent "
                f"{initial['actor_label']} at source transform key "
                f"frame={initial['first_frame']}."
            )

        for edge in pending:
            child = actors[edge["actor_label"]]
            parent = actors[edge["parent_actor_label"]]
            initial_world = child.get_actor_transform()
            rule = unreal.AttachmentRule.KEEP_WORLD
            attached = child.attach_to_actor(
                parent, unreal.Name("None"), rule, rule, rule, False
            )
            if attached is False or child.get_attach_parent_actor() is not parent:
                # Catch the case where Unreal partially attaches before returning.
                if child.get_attach_parent_actor() is parent:
                    _detach_keep_world(child)
                    _restore_transform(child, initial_world)
                raise UnrealHierarchyError(
                    f"Unreal rejected attachment "
                    f"{edge['actor_label']} -> {edge['parent_actor_label']}."
                )
            changes.append({
                "kind": "new_attachment",
                "child": child,
                "previous_world_transform": initial_world,
            })
            unreal.log(
                "[CineTwin] Verified actor attachment "
                f"{edge['actor_label']} -> {edge['parent_actor_label']} "
                "(KEEP_WORLD; weld_simulated_bodies=False)"
            )
    except Exception:
        rollback_hierarchy(changes)
        raise

    unreal.log_warning(
        "[CineTwin] Actor hierarchy changed in editor memory. The Unreal level "
        "has NOT been saved by the generator. Verify evaluated child motion and "
        "save an approved target copy separately."
    )
    return changes
