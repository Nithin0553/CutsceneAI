"""Phase 10.2 multi-character frame coordination and hierarchy ownership.

Pure source/target evidence. This module does not synthesize native Unreal
commands: actor-world trajectory and retargeted skeletal-root ownership are
different authorities, even if positions happen to match.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

import character_motion


class CharacterSyncError(ValueError):
    """Source character identity, timing, or hierarchy cannot be established."""


MAX_CHARACTERS = 32
MAX_PAIR_CHECKS = MAX_CHARACTERS * (MAX_CHARACTERS - 1) // 2
MAX_WORLD_ERROR_CM = 100000.0


def _digest(value: Any) -> str:
    raw = json.dumps(
        value, sort_keys=True, separators=(",",":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _parent_order(entities: list[dict]) -> list[str]:
    by_id = {}
    for entity in entities:
        if not isinstance(entity,dict):
            raise CharacterSyncError("Malformed source entity in hierarchy.")
        identity = entity.get("entity_id")
        if not isinstance(identity,str) or not identity or identity in by_id:
            raise CharacterSyncError("Duplicate or missing source entity identity.")
        by_id[identity] = entity
    visiting, visited, order = set(), set(), []
    def visit(identity):
        if identity in visiting:
            raise CharacterSyncError("Source character/scene hierarchy has a cycle.")
        if identity in visited:
            return
        visiting.add(identity)
        parent = by_id[identity].get("parent_entity_id")
        if parent:
            if parent not in by_id:
                raise CharacterSyncError("Unresolved source parent in actor hierarchy.")
            visit(parent)
        visiting.remove(identity)
        visited.add(identity)
        order.append(identity)
    for identity in by_id:
        visit(identity)
    return order


def _frame_poses(capture: dict, identifiers: list[str],
                 times: list[float], *, target: bool = False,
                 labels: dict[str,str] | None = None) -> dict[str,list[dict]]:
    if not isinstance(capture,dict) or not isinstance(capture.get("samples"),list):
        raise CharacterSyncError("Source/native capture sample inventory is missing.")
    rows = {}
    for sample in capture["samples"]:
        if (not isinstance(sample,dict)
                or type(sample.get("time_seconds")) not in (float,int)
                or not math.isfinite(sample["time_seconds"])):
            raise CharacterSyncError("Camera/character capture timestamps are malformed.")
        second = round(float(sample["time_seconds"]),8)
        if second in rows:
            raise CharacterSyncError("Character capture has duplicate timestamps.")
        rows[second] = sample
    result = {ident:[] for ident in identifiers}
    for second in times:
        frame = rows.get(round(second,8))
        if not isinstance(frame,dict) or not isinstance(frame.get("entities"),list):
            raise CharacterSyncError("Complete multi-character frame sample is missing.")
        entities = frame["entities"]
        for ident in identifiers:
            matches = [e for e in entities if isinstance(e,dict)
                       and e.get("entity_id") == ident]
            if len(matches)!=1:
                raise CharacterSyncError("Character frame source identity is not unique.")
            observed = matches[0]
            if target and labels is not None and observed.get("actor_label") != labels[ident]:
                raise CharacterSyncError("Native character actor binding is not source mapped.")
            transform = observed.get("world_transform")
            if not isinstance(transform,dict):
                raise CharacterSyncError("Character world pose is unavailable.")
            position = transform.get("position_m")
            rotation = transform.get("rotation_xyzw")
            if (not isinstance(position,(list,tuple)) or len(position)!=3
                    or any(type(x) not in (int,float) or not math.isfinite(x)
                           for x in position)):
                raise CharacterSyncError("Character world position is malformed.")
            character_motion.conjugate(rotation)
            result[ident].append({
                "position_m":tuple(float(x) for x in position),
                "rotation_xyzw":tuple(float(x) for x in rotation),
            })
    return result


def _rotation_error(a: tuple,b: tuple) -> float:
    delta = abs(sum(x*y for x,y in zip(a,b)))
    return math.degrees(2*math.acos(min(1.,max(-1.,delta))))


def analyze(csir: dict[str,Any], source: dict[str,Any], *,
            mapping: dict[str,Any] | None = None,
            target: dict[str,Any] | None = None,
            position_tolerance_cm: float = 1.0,
            rotation_tolerance_degrees: float = 0.5) -> dict[str,Any]:
    """Measure all mapped characters on one strict display-frame grid.

    Only positions/orientations are compared. Native retargeted bone pose,
    actual authored root-motion owner, contact, physics, and parent animation
    remain independently unverified even if the actor-world paths match.
    """
    if not isinstance(csir,dict) or not isinstance(csir.get("entities"),list):
        raise CharacterSyncError("Original source entity census missing.")
    if (type(position_tolerance_cm) not in (int,float)
            or type(rotation_tolerance_degrees) not in (int,float)
            or not math.isfinite(position_tolerance_cm)
            or not math.isfinite(rotation_tolerance_degrees)
            or not 0 <= position_tolerance_cm <= 100
            or not 0 <= rotation_tolerance_degrees <= 10):
        raise CharacterSyncError("Comparison tolerances must be finite and bounded.")
    all_entities = csir["entities"]
    order = _parent_order(all_entities)
    characters = [entity for entity in all_entities
                  if entity.get("ced_type") == "entity.character"]
    if not 1 <= len(characters) <= MAX_CHARACTERS:
        raise CharacterSyncError("Source multi-character scene exceeds character budget.")
    identifiers = [e["entity_id"] for e in characters]
    if len(set(identifiers)) != len(identifiers):
        raise CharacterSyncError("Source character IDs are ambiguous.")
    trajectories = {}
    for ident in identifiers:
        try:
            trajectories[ident] = character_motion.trajectory(csir,source,ident)
        except (character_motion.MotionError, KeyError,TypeError,ValueError) as exc:
            raise CharacterSyncError(
                "Every source character requires its complete original world trajectory."
            ) from exc
    rate = trajectories[identifiers[0]]["display_rate"]
    keys = trajectories[identifiers[0]]["keys"]
    duration = trajectories[identifiers[0]]["duration_frames"]
    if any(item["display_rate"]!=rate
           or item["duration_frames"]!=duration
           or [key["frame"] for key in item["keys"]] != list(range(duration+1))
           for item in trajectories.values()):
        raise CharacterSyncError("Characters do not share one complete display-frame grid.")
    times = [frame*rate["denominator"]/rate["numerator"]
             for frame in range(duration+1)]
    samples = _frame_poses(source, identifiers, times)
    labels = None
    if mapping is not None:
        if not isinstance(mapping,dict) or not isinstance(mapping.get("entities"),dict):
            raise CharacterSyncError("Target character mapping is missing.")
        labels = {}
        used = set()
        for entity in characters:
            row = mapping["entities"].get(entity.get("name"))
            label = row.get("actor_label") if isinstance(row,dict) else None
            if (not isinstance(label,str) or not label
                    or label in used):
                raise CharacterSyncError("Source/native character actor label is ambiguous.")
            labels[entity["entity_id"]] = label
            used.add(label)
    native_samples = (_frame_poses(target,identifiers,times,target=True,labels=labels)
                      if target is not None else None)
    per_character = []
    for entity in characters:
        ident = entity["entity_id"]
        positions = samples[ident]
        observed = native_samples[ident] if native_samples is not None else None
        drift_cm = max(
            math.dist(a["position_m"],b["position_m"])*100
            for a,b in zip(positions,observed)
        ) if observed else None
        rotation_deg = max(
            _rotation_error(a["rotation_xyzw"],b["rotation_xyzw"])
            for a,b in zip(positions,observed)
        ) if observed else None
        if drift_cm is not None and (
                not math.isfinite(drift_cm) or drift_cm > MAX_WORLD_ERROR_CM):
            raise CharacterSyncError("Source/native actor drift is nonfinite or unbounded.")
        per_character.append({
            "source_entity_id":ident,
            "source_name":entity.get("name"),
            "parent_entity_id":entity.get("parent_entity_id"),
            "mapped_native_label":labels[ident] if labels else None,
            "source_trajectory_sha256":_digest(trajectories[ident]),
            "source_sample_count":len(positions),
            "native_sample_count":len(observed) if observed else 0,
            "maximum_actor_world_drift_cm":drift_cm,
            "maximum_actor_facing_delta_degrees":rotation_deg,
            "actor_world_comparison_within_tolerance": (
                drift_cm <= position_tolerance_cm
                and rotation_deg <= rotation_tolerance_degrees
            ) if observed else None,
            "native_animated_hierarchy_verified":False,
            "native_bone_pose_verified":False,
            "native_root_motion_owner_verified":False,
        })
    # Source relative separation describes coordination but does not imply
    # contacts/IK or physics matches. Includes multi-character frames only.
    pairs=[]
    for i,first in enumerate(identifiers):
        for second in identifiers[i+1:]:
            distances=[math.dist(a["position_m"],b["position_m"])
                       for a,b in zip(samples[first],samples[second])]
            pairs.append({
                "source_pair_ids":[first,second],
                "minimum_source_separation_m":min(distances),
                "maximum_source_separation_m":max(distances),
                "contact_or_physics_equivalence_verified":False,
            })
    assert len(pairs) <= MAX_PAIR_CHECKS
    report = {
        "kind":"cutsceneai.studio.phase10_2.character_synchronization",
        "schema_version":"1",
        "source_character_count":len(characters),
        "source_hierarchy_topological_order":order,
        "shared_frame_count":len(keys),
        "display_rate":rate,
        "per_character":per_character,
        "source_pair_distances":pairs,
        "native_source_binding_checked":labels is not None and target is not None,
        "independently_reopened_native_cinetwin_verified":False,
        "native_animation_or_retarget_execution_authorized":False,
        "full_cutscene_fidelity_verified":False,
    }
    report["source_bound_report_sha256"]=_digest(report)
    return report
