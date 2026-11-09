"""Source-authenticated skeletal-root alignment plan (Unreal-independent).

An evaluated source rig root is an observable point on the character, not
necessarily the Unity actor origin. Per-frame world-root targets let the Unreal
adapter counteract root-bone resets during overlapping animation sections.
This guarantees neither full joint-pose parity nor the motion of attached actors.
"""
from __future__ import annotations

import math
import re
from typing import Any

import csir_plan


class RootWorldLockError(ValueError):
    pass


def bone_alias(bone_id: str) -> str:
    leaf = str(bone_id).rsplit("/", 1)[-1]
    return re.sub(r"\[\d+\]$", "", leaf).rsplit(":", 1)[-1].casefold()


def source_root_world_keys(
    csir: dict[str, Any], capture: dict[str, Any], entity: dict[str, Any],
) -> dict[str, Any]:
    entity_id = str(entity["entity_id"])
    rig = [r for r in capture.get("rigs", [])
           if str(r.get("entity_id")) == entity_id]
    if len(rig) != 1:
        raise RootWorldLockError("Expected one observed source skeletal rig for " + entity["name"])
    root_bones = [b for b in rig[0].get("bones", [])
                  if not str(b.get("parent_bone_id", ""))]
    if len(root_bones) != 1:
        raise RootWorldLockError(
            "Ambiguous source rig root; map root explicitly before correction: "
            + entity["name"]
        )
    root = str(root_bones[0]["bone_id"])
    alias = bone_alias(root)
    fps = csir["timing"].get("display_rate") or csir["timing"]["source_rate"]
    hz = float(fps["numerator"]) / float(fps["denominator"])
    first = csir_plan.rational_seconds(csir["timing"]["playback_start"])
    end = csir_plan.rational_seconds(csir["timing"]["playback_end"])
    count = int(math.floor((end - first) * hz + 1e-7))
    samples_by_time = {round(float(s["time_seconds"]), 8): s
                       for s in capture["samples"]}
    keys: list[dict[str, Any]] = []
    for frame in range(count):
        time = first + frame / hz
        sample = samples_by_time.get(round(time, 8))
        if sample is None:
            raise RootWorldLockError(
                f"Missing authenticated root-pose frame for {entity['name']}: {frame}"
            )
        matching_rigs = [p for p in sample.get("skeletal_poses", [])
                         if str(p.get("entity_id")) == entity_id]
        if len(matching_rigs) != 1:
            raise RootWorldLockError(
                f"Missing or ambiguous source bone pose for {entity['name']}: {frame}"
            )
        matching_bones = [b for b in matching_rigs[0].get("bones", [])
                          if str(b.get("bone_id")) == root]
        if len(matching_bones) != 1:
            raise RootWorldLockError(
                f"Missing root bone {root} at source frame {frame}"
            )
        position = matching_bones[0]["world_transform"]["position_m"]
        xyz = csir_plan.canonical_position_to_unreal_cm(
            tuple(float(value) for value in position)
        )
        if not all(math.isfinite(value) for value in xyz):
            raise RootWorldLockError("Nonfinite source root pose at frame " + str(frame))
        keys.append({"frame": frame, "source_root_world_cm": list(xyz)})
    if not keys:
        raise RootWorldLockError("No source root bone poses sampled for " + entity["name"])
    excursion = max(
        math.dist(keys[0]["source_root_world_cm"], key["source_root_world_cm"])
        for key in keys
    )
    return {
        "root_source_bone_id": root,
        "root_bone_alias": alias,
        "keys": keys,
        "source_root_excursion_cm": excursion,
    }


def corrected_actor_location_cm(
    source_root_world_cm: list[float] | tuple[float, ...],
    observed_target_root_world_cm: tuple[float, ...],
    observed_target_actor_world_cm: tuple[float, ...],
) -> tuple[float, float, float]:
    """Translate actor so its evaluated target skeletal root matches source world root."""
    if any(len(v) != 3 for v in (
        source_root_world_cm, observed_target_root_world_cm,
        observed_target_actor_world_cm,
    )):
        raise RootWorldLockError("Expected three XYZ positions.")
    values = tuple(float(v) for positions in (
        source_root_world_cm, observed_target_root_world_cm,
        observed_target_actor_world_cm,
    ) for v in positions)
    if not all(math.isfinite(v) for v in values):
        raise RootWorldLockError("Nonfinite skeletal root world correction inputs.")
    return tuple(
        float(observed_target_actor_world_cm[i])
        + float(source_root_world_cm[i])
        - float(observed_target_root_world_cm[i])
        for i in range(3)
    )
