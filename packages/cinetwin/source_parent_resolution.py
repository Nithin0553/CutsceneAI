"""Identify static Unity grouping ancestry and world-space-baked alternatives.

Never equate world-space placement with source grouping/editability or playback
fidelity. Dynamic ancestors and unknown coordinate ownership remain unresolved.
"""
from __future__ import annotations

import math
from typing import Any

from hierarchy_plan import plan_actor_hierarchy


def _valid_world(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    for part, fields in (("position", "xyz"), ("rotation", "xyzw"), ("scale", "xyz")):
        data = value.get(part)
        if not isinstance(data, dict):
            return False
        try:
            vals = [float(data[key]) for key in fields]
        except (KeyError, TypeError, ValueError):
            return False
        if not all(math.isfinite(v) for v in vals):
            return False
        if part == "scale" and any(abs(v) < 1e-8 for v in vals):
            return False
        if part == "rotation" and not 0.95 <= math.sqrt(sum(v*v for v in vals)) <= 1.05:
            return False
    return True


def analyze(csir: dict[str, Any], mapping: dict[str, Any],
            actions: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify every missing immediate parent using real source IDs and actions."""
    hierarchy = plan_actor_hierarchy(csir, mapping)
    by_id = {str(e["entity_id"]): e for e in csir.get("entities", [])}
    active_tracks = {str(t.get("binding_entity_id"))
                     for t in csir.get("tracks", [])
                     if not t.get("muted") and t.get("sections")}
    by_name: dict[str, list[dict[str, Any]]] = {}
    for action in actions:
        by_name.setdefault(str(action.get("entity_name")), []).append(action)
    rows = []
    for missing in hierarchy["unresolved_source_parents"]:
        chain = []
        cursor = str(missing["source_parent_entity_id"])
        visited = set()
        while cursor and cursor not in visited:
            visited.add(cursor)
            ancestor = by_id[cursor]
            metadata = ancestor.get("metadata") or {}
            animator = metadata.get("animator") or {}
            is_static = (
                ancestor.get("ced_type") == "entity.prop"
                and cursor not in active_tracks
                and metadata.get("active_self") is True
                and bool(metadata.get("hierarchy_path"))
                and _valid_world(metadata.get("world_transform"))
                and not animator.get("apply_root_motion")
                and not animator.get("has_avatar")
                and not any(metadata.get(k) for k in (
                    "scripts", "components", "mesh_asset_id", "constraint", "physics"))
            )
            chain.append({"id": cursor, "name": ancestor["name"],
                          "static_container_candidate": is_static})
            if ancestor["name"] in mapping.get("entities", {}):
                break
            cursor = str(ancestor.get("parent_entity_id") or "")
        actor = by_id[missing["entity_id"]]
        transforms = [a for a in by_name.get(missing["entity_name"], [])
                      if a.get("kind") == "transform"]
        static_pose = (
            len(transforms) == 1
            and transforms[0].get("source_behavior_strategy") in {
                "source_static_world_pose", "cinetwin_verified_first_frame_static_actor"}
            and len(transforms[0].get("keys", [])) == 1
            and _valid_world(actor.get("metadata", {}).get("world_transform")))
        world_motion = (
            len(transforms) == 1
            and transforms[0].get("source_behavior_strategy") in {
                "captured_untracked_world_motion", "verified_cinetwin_camera_world_pose"}
            and bool(transforms[0].get("keys")))
        # The deterministic CSIR adapter itself composes source Transform
        # ancestry into world-space keys. Retain the exact native/baked curve
        # distinction rather than misclassifying it as a missing hierarchy.
        csir_world_curve = (
            len(transforms) == 1
            and transforms[0].get("baked_source_curves") is True
            and not transforms[0].get("transform_space")
            and bool(transforms[0].get("keys"))
            and not transforms[0].get("source_behavior_strategy")
        )
        if not chain or not all(part["static_container_candidate"] for part in chain):
            strategy = "PARENT_BEHAVIOR_UNVERIFIED"
        elif world_motion:
            strategy = "CAPTURED_WORLD_MOTION_PLANNED_UNVERIFIED"
        elif csir_world_curve:
            strategy = "CSIR_PARENT_COMPOSED_WORLD_CURVE_PLANNED_UNVERIFIED"
        elif static_pose:
            strategy = "STATIC_WORLD_POSE_REPRESENTED_UNVERIFIED"
        else:
            strategy = "CHILD_WORLD_BEHAVIOR_UNVERIFIED"
        rows.append({
            "entity_id": missing["entity_id"],
            "source_name": missing["entity_name"],
            "target_actor_label": missing["actor_label"],
            "ancestor_chain": chain,
            "strategy": strategy,
            "native_parent_actor_reconstructed": False,
            "group_editability_preserved": False,
            "target_runtime_verified": False,
        })
    return {
        "kind": "cutsceneai.source_parent_resolution",
        "schema_version": "0.1.0",
        "total": len(rows),
        "static_pose_candidates": sum(r["strategy"] ==
            "STATIC_WORLD_POSE_REPRESENTED_UNVERIFIED" for r in rows),
        "captured_world_motion_candidates": sum(r["strategy"] ==
            "CAPTURED_WORLD_MOTION_PLANNED_UNVERIFIED" for r in rows),
        "rows": rows,
        "fidelity_verified": False,
        "note": "World-pose coverage is not native source hierarchy or verified playback equivalence.",
    }
