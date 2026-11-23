"""Source-measured rigid actor motion; no inferred root offsets or engine calls."""
from __future__ import annotations

import math
import re
from fractions import Fraction


ACTION = "bake_verified_actor_world_trajectory"
OWNER = "ACTOR_WORLD_TRAJECTORY_WITH_STATIC_SKELETAL_ROOT"
STRATEGY = "cinetwin_verified_actor_world_trajectory_v1"
LOCAL_OWNER = "ACTOR_WITH_STABLE_LOCAL_ROOT"
MAX_FRAMES = 4000
STILL_CM = 0.1
STILL_DEGREES = 0.1


class MotionError(ValueError):
    pass


def conjugate(q):
    """Unit inverse; reject invalid source poses before applying any root correction."""
    if (not isinstance(q, (list,tuple)) or len(q) != 4
            or any(type(v) not in (int,float) or not math.isfinite(v)
                   for v in q)):
        raise MotionError("Invalid observed actor/root quaternion.")
    length = math.hypot(*q)
    if (not math.isfinite(length) or length == 0
            or not math.isclose(length, 1, abs_tol=0.01)):
        raise MotionError("Invalid observed actor/root quaternion.")
    return [-q[0] / length, -q[1] / length, -q[2] / length, q[3] / length]


def multiply(a, b):
    x, y, z, w = a
    i, j, k, s = b
    return [w*i + x*s + y*k - z*j, w*j - x*k + y*s + z*i,
            w*k + x*j - y*i + z*s, w*s - x*i - y*j - z*k]


def relative_root(actor, root):
    """Measured actor-local skeletal root, including 3-D facing and translation.

    Reject missing axes and non-unit quaternions. Component-space data is not
    interchangeable with actor-world root motion, especially during turns.
    """
    if not isinstance(actor, dict) or not isinstance(root, dict):
        raise MotionError("Missing observed actor/root world transform.")
    for row in (actor,root):
        pos = row.get("position_m")
        if (not isinstance(pos,(list,tuple)) or len(pos) != 3
                or any(type(v) not in (int,float) or not math.isfinite(v)
                       for v in pos)):
            raise MotionError("Actor/root world position must be three finite axes.")
    inverse = conjugate(actor.get("rotation_xyzw"))
    root_inverse = conjugate(root.get("rotation_xyzw"))
    # Preserve a normalized root input, regardless of the quaternion sign.
    normalized_root = [-root_inverse[0],-root_inverse[1],
                       -root_inverse[2],root_inverse[3]]
    delta = [r - a for r, a in zip(root["position_m"],actor["position_m"])]
    position = multiply(multiply(inverse,[*delta,0.]),conjugate(inverse))[:3]
    relative_orientation = multiply(inverse,normalized_root)
    if not all(math.isfinite(x) for x in (*position,*relative_orientation)):
        raise MotionError("Relative root pose contains nonfinite components.")
    return position,relative_orientation


def _seconds(value):
    rate = value["rate"]
    result = Fraction(value["value"]) * Fraction(rate["denominator"], rate["numerator"])
    if value.get("subframe"):
        subframe = value["subframe"]
        result += Fraction(subframe["numerator"], subframe["denominator"]) * Fraction(rate["denominator"], rate["numerator"])
    return result


def trajectory(csir, capture, identifier):
    """Include the measured exclusive-end boundary key for exact interpolation.

    Playback remains [0, duration). The transform section includes the sampled
    boundary at duration. Keys use display frames, not ticks.
    Subframe source samples remain classification evidence, never rounded keys.
    """
    import csir_plan
    timing = csir["timing"]
    rate = timing.get("display_rate") or timing["source_rate"]
    hz = Fraction(rate["numerator"], rate["denominator"])
    start, end = [_seconds(timing[k]) for k in ("playback_start", "playback_end")]
    count = (end - start) * hz
    if rate != timing["source_rate"] or not math.isclose(float(end - start), timing["duration_seconds"], abs_tol=1e-8, rel_tol=0):
        raise MotionError("MOVING_ACTOR_REQUIRES_MATCHED_SOURCE_DISPLAY_RATE_AND_DURATION")
    if hz <= 0 or hz > 240 or start != 0 or count.denominator != 1 or not 1 <= count < MAX_FRAMES:
        raise MotionError("MOVING_ACTOR_REQUIRES_BOUNDED_INTEGRAL_DISPLAY_FRAME_RANGE")
    by_time = {}
    if not isinstance(capture,dict) or not isinstance(capture.get("samples"),list):
        raise MotionError("MISSING_SOURCE_ACTOR_CAPTURE")
    for sample in capture["samples"]:
        if not isinstance(sample,dict) or type(sample.get("time_seconds")) not in (int,float):
            raise MotionError("INVALID_SOURCE_ACTOR_TIMESTAMP")
        raw_time = sample["time_seconds"]
        if not math.isfinite(raw_time) or not 0 <= raw_time <= float(end):
            raise MotionError("OUT_OF_RANGE_SOURCE_ACTOR_TIMESTAMP")
        time = round(raw_time,8)
        if time in by_time:
            raise MotionError("DUPLICATE_SOURCE_TIMESTAMP")
        by_time[time] = sample
    keys, previous = [], None
    for frame in range(int(count) + 1):
        sample = by_time.get(round(float(start + frame / hz), 8))
        if sample is None:
            raise MotionError("MISSING_EXACT_SOURCE_DISPLAY_FRAME")
        entities = sample.get("entities")
        if not isinstance(entities,list):
            raise MotionError("MISSING_SOURCE_ACTOR_FRAME_ENTITIES")
        poses = [e for e in entities
                 if isinstance(e,dict) and e.get("entity_id") == identifier]
        if len(poses) != 1:
            raise MotionError("AMBIGUOUS_SOURCE_ACTOR_FRAME")
        pose = poses[0].get("world_transform")
        if not isinstance(pose,dict):
            raise MotionError("MISSING_SOURCE_ACTOR_WORLD_TRANSFORM")
        conjugate(pose.get("rotation_xyzw"))
        raw_pos = pose.get("position_m")
        if (not isinstance(raw_pos,(tuple,list)) or len(raw_pos)!=3
                or any(type(v) not in (int,float) or not math.isfinite(v)
                       for v in raw_pos)):
            raise MotionError("INVALID_SOURCE_ACTOR_WORLD_POSITION")
        position = csir_plan.canonical_position_to_unreal_cm(raw_pos)
        rotation = csir_plan.continuous_unreal_rotator(
            previous, csir_plan.canonical_quat_to_unreal_rotator(pose["rotation_xyzw"])
        )
        if not all(math.isfinite(v) for v in (*position, *rotation)):
            raise MotionError("NONFINITE_SOURCE_ACTOR_FRAME")
        previous = rotation
        keys.append({"frame": frame, "location_cm": list(position), "rotation_rpy_degrees": list(rotation)})
    return {"display_rate": rate, "duration_frames": int(count), "source_start_seconds": float(start), "keys": keys}


def binding(mapping, report, row):
    return {"sequence_asset_path": mapping["sequence_asset_path"], "target_actor_label": row["target_actor_label"],
            "source_entity_id": row["source_entity_id"], "worker": report["target_probe"],
            "source_capture_sha256": report["context"]["input_sha256"]["capture"],
            "trajectory_sha256": row["motion"]["trajectory_sha256"]}


def apply_plan(plan, mapping, csir, capture):
    """One installed owner replaces existing actor keys; legacy root owners refuse."""
    decision = mapping.get("ai_character_animation") or {}
    if decision.get("action_id") != ACTION:
        return
    identifier = decision["source_entity_id"]
    entity, = [e for e in csir["entities"] if e["entity_id"] == identifier]
    if capture is None or entity.get("parent_entity_id") or mapping.get("enable_cinetwin_skeletal_world_lock"):
        raise MotionError("Moving actor requires measured, unparented motion and one motion owner.")
    data = trajectory(csir, capture, identifier)
    actions = [a for a in plan["actions"] if a.get("entity_name") == entity["name"]]
    clips = [a for a in actions if a["kind"] == "skeletal_animation"]
    if (not clips or any(a["kind"] == "skeletal_world_root_lock" or
                        any(k in a for k in ("expected_root_delta_cm", "root_motion_source_samples", "root_motion_source_profile"))
                        for a in actions)):
        raise MotionError("Moving actor refuses another root-motion trajectory or correction.")
    for clip in clips:
        clip["hold_end_frame"] = data["duration_frames"] + 1
    plan["actions"] = [a for a in plan["actions"] if not
                       (a.get("entity_name") == entity["name"] and a["kind"] == "transform")]
    asset, = [a for a in csir["assets"] if any(s.get("payload", {}).get("asset_id") == a["asset_id"]
              for t in csir["tracks"] if t.get("binding_entity_id") == identifier for s in t.get("sections", []))]
    timing = asset["metadata"]["animation_clip"]
    plan["actions"].append({"kind": "transform", "entity_name": entity["name"],
                            "actor_label": mapping["entities"][entity["name"]]["actor_label"],
                            "track_name": "CutSceneAI Verified Actor World Motion", "keys": data["keys"],
                            "baked_source_curves": True, "source_behavior_strategy": STRATEGY,
                            "motion_ownership": OWNER, "source_entity_id": identifier,
                            "native_root_sample_rate": timing["frame_rate"],
                            "native_root_duration_seconds": timing["duration_seconds"]})
    plan["ai_character_motion_binding"] = mapping["ai_character_motion_binding"]


def receipt_matches(receipt, plan):
    """Extra proof required by the existing audit and canonical release gate."""
    if (plan.get("ai_character_animation") or {}).get("action_id") != ACTION:
        return True
    proof = receipt.get("motion") or {}
    binding = plan.get("ai_character_motion_binding") or {}
    if not isinstance(proof, dict) or not isinstance(binding, dict):
        return False
    roots = proof.get("native_roots") or {}
    if not isinstance(roots, dict) or not isinstance(roots.get("roots"), list):
        return False
    transforms = [a for a in plan.get("actions", []) if a.get("source_entity_id") == binding.get("source_entity_id")
                  and a.get("kind") == "transform"]
    if len(transforms) != 1:
        return False
    clips = {a["unreal_asset_path"] for a in plan["actions"] if a.get("entity_name") == transforms[0]["entity_name"]
             and a.get("kind") == "skeletal_animation"}
    if {r.get("clip") for r in roots["roots"] if isinstance(r, dict)} != clips:
        return False
    for root in roots["roots"]:
        if not isinstance(root, dict):
            return False
        for field, limit in (("maximum_translation_cm", STILL_CM), ("maximum_rotation_degrees", STILL_DEGREES)):
            value = root.get(field)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= limit:
                return False
        if (type(root.get("sample_count")) is not int or not 2 <= root["sample_count"] <= 2 * MAX_FRAMES
                or not re.fullmatch(r"[a-f0-9]{64}", str(root.get("raw_root_samples_sha256", "")))):
            return False
    return bool(binding and proof.get("status") == "PASS" and proof.get("motion_ownership") == OWNER
                and proof.get("trajectory_sha256") == binding.get("trajectory_sha256")
                and proof.get("display_rate") == plan.get("display_rate")
                and proof.get("frame_count") == plan.get("duration_frames", -2) + 1
                and proof.get("owning_actor_binding_count") == proof.get("transform_track_count") == 1
                and proof.get("section_start_frame") == 0
                and proof.get("section_end_frame") == plan.get("duration_frames", -2) + 1
                and roots.get("status") == "PASS" and len(roots.get("roots") or []) == 1
                and all(r.get("status") == "PASS" for r in roots["roots"])
                and re.fullmatch(r"[a-f0-9]{64}", str(proof.get("observed_channels_sha256", "")))
                and proof.get("fidelity_verified") is False)
