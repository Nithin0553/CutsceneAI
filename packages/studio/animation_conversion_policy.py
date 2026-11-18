"""Registered pre-transfer animation choices and immutable plan checks."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import character_compatibility as compatibility
import csir_plan
import character_motion as motion

PROBE_REQUEST = "character-probe-request.json"
PROBE_RESULT = "character-probe-result.json"
REPORT_FILE = "character-compatibility.json"
NATIVE_FILE = "character-native-execution.json"
ACTION = "use_approved_ik_retarget_profile"
CATALOG = {ACTION: {"version": "1", "capability_id": "unreal.ik_retarget.batch",
                    "motion_ownership": "IN_PLACE_NATIVE_SKELETAL_CLIP"},
           motion.ACTION: {"version": "1", "capability_id": "unreal.character.actor_world_trajectory",
                           "motion_ownership": motion.OWNER}}


def action_for(row):
    if row["status"] in ("COMPATIBLE", "COMPATIBLE_AFTER_APPROVED_RETARGET") and row["motion"]["owner"] == motion.LOCAL_OWNER:
        return motion.ACTION
    return ACTION if row["status"] == "COMPATIBLE_AFTER_APPROVED_RETARGET" else None


def make_probe_request(config: dict, csir: dict, mapping: dict, *, run_id: str = "") -> dict | None:
    if not config.get("unity_project"):
        return None
    characters = {entity["entity_id"] for entity in csir.get("entities", [])
                  if entity.get("ced_type") == "entity.character"}
    asset_names = {asset["asset_id"]: asset.get("name") for asset in csir.get("assets", [])}
    tracks = [track for track in csir.get("tracks", []) if track.get("ced_type") == "animation.track"
              and track.get("muted") is not True and track.get("binding_entity_id") in characters
              and track.get("sections")]
    if not tracks:
        return None
    context, profiles = compatibility.input_context(config, csir)
    selected = {track["binding_entity_id"] for track in tracks}
    paths = set()
    for track in tracks:
        for section in track["sections"]:
            asset_id = (section.get("payload") or {}).get("asset_id")
            path = (mapping.get("assets") or {}).get(asset_names.get(asset_id))
            if isinstance(path, str) and compatibility.PACKAGE_PATH.fullmatch(path):
                paths.add(path)
    return {"kind": "cutsceneai.studio.character_probe_request", "schema_version": "1", "run_id": run_id,
            "context": context, "context_sha256": compatibility.probe_identity(context),
            "profile_ids": sorted(selected & profiles.keys()), "clip_paths": sorted(paths)[:64]}


def report_for_model(report: dict) -> dict:
    """The only character evidence serialized into the model request."""
    rows = [{"choice_id": row["id"], "status": row["status"], "motion_owner": row["motion"]["owner"],
             "source_clip_count": len(row["clips"]), "target_material_policy": row["material_status"],
             "measured_source_frames": row["motion"].get("sample_count", 0),
             "source_actor_translation_cm": round(row["motion"].get("actor_translation_cm", 0), 2)
             if "actor_translation_cm" in row["motion"] else None,
             "source_skeletal_root_translation_cm": round(row["motion"].get("root_translation_cm", 0), 2)
             if "root_translation_cm" in row["motion"] else None,
             "source_actor_rotation_degrees": round(row["motion"].get("actor_rotation_degrees", 0), 2)
             if "actor_rotation_degrees" in row["motion"] else None,
             "source_skeletal_root_rotation_degrees": round(row["motion"].get("root_rotation_degrees", 0), 2)
             if "root_rotation_degrees" in row["motion"] else None,
             "target_ik_rig_observed": row["target"].get("status") == "OBSERVED",
             "approved_action": action_for(row)}
            for row in report["characters"][:12]]
    return {"rows": rows, "character_count": report["character_count"]}


def available_choices(report: dict) -> list[str]:
    return [row["choice_id"] for row in report_for_model(report)["rows"] if row["approved_action"] in CATALOG]


def decision_for(report: dict, choice: str) -> dict:
    if choice not in available_choices(report):
        raise compatibility.CompatibilityError("The requested animation action lacks verified eligible evidence.")
    row, = [r for r in report["characters"] if r["id"] == choice]
    action = action_for(row)
    return {"kind": "cutsceneai.studio.ai_animation_conversion_decision", "schema_version": "1",
            "choice_id": choice, "action_id": action, **CATALOG[action],
            "source_entity_id": row["source_entity_id"], "evidence_ids": row["evidence_ids"],
            "compatibility_report_sha256": compatibility.digest(report)}


def selected(report: dict, decision: dict) -> dict:
    if not isinstance(decision, dict) or decision != decision_for(report, decision.get("choice_id")):
        raise compatibility.CompatibilityError("Stale or unregistered animation decision, or changed source/target evidence.")
    row, = [r for r in report["characters"] if r["id"] == decision["choice_id"]]
    return row


def apply_mapping(mapping: dict, report: dict, decision: dict) -> None:
    row = selected(report, decision)
    original = mapping.get("skeletal_retarget_profiles", {})
    if not isinstance(original, dict) or row["source_entity_id"] in original:
        raise compatibility.CompatibilityError("AI animation choice conflicts with the explicitly mapped retarget profile.")
    mapping["skeletal_retarget_profiles"] = {**original, row["source_entity_id"]: row["approved_profile"]}
    mapping["ai_character_animation"] = decision
    if decision["action_id"] == motion.ACTION:
        if mapping["sequence_asset_path"] == report["context"]["original_sequence_path"]:
            raise compatibility.CompatibilityError("Moving character requires an isolated new candidate sequence.")
        mapping["ai_character_motion_binding"] = motion.binding(mapping, report, row)


def verify_plan(report: dict, decision: dict, mapping: dict, plan: dict, manifest: dict) -> dict:
    row = selected(report, decision)
    name, identifier = row["source_entity_name"], row["source_entity_id"]
    profile = row["approved_profile"]
    if (mapping.get("ai_character_animation") != decision or plan.get("ai_character_animation") != decision
            or mapping.get("skeletal_retarget_profiles", {}).get(identifier) != profile
            or manifest.get("skeletal_retarget_profiles", {}).get(name) != {**profile, "source_entity_id": identifier}
            or plan.get("bindings", {}).get(name) != row["target_actor_label"] or not manifest.get("ready")):
        raise compatibility.CompatibilityError("Prepared native retarget mapping differs from approved animation evidence.")
    actions = [a for a in plan["actions"] if a.get("entity_name") == name]
    moving = decision["action_id"] == motion.ACTION
    if moving:
        expected_binding = motion.binding(mapping, report, row)
        transforms = [a for a in actions if a["kind"] == "transform"]
        path = row["motion"]["trajectory"]
        if (mapping["sequence_asset_path"] == report["context"]["original_sequence_path"]
                or plan["sequence_asset_path"] != mapping["sequence_asset_path"]
                or mapping.get("ai_character_motion_binding") != expected_binding
                or plan.get("ai_character_motion_binding") != expected_binding
                or plan["display_rate"] != path["display_rate"] or plan["duration_frames"] != path["duration_frames"]
                or len(transforms) != 1 or transforms[0].get("keys") != path["keys"]
                or transforms[0].get("source_behavior_strategy") != motion.STRATEGY
                or transforms[0].get("motion_ownership") != motion.OWNER
                or transforms[0].get("native_root_sample_rate") != row["clips"][0]["timing"]["source_fps"]
                or transforms[0].get("native_root_duration_seconds") != row["clips"][0]["timing"]["duration_seconds"]
                or transforms[0].get("actor_label") != row["target_actor_label"]
                or transforms[0].get("source_entity_id") != identifier or not transforms[0].get("baked_source_curves")):
            raise compatibility.CompatibilityError("Moving actor trajectory, worker, frame grid or candidate binding changed.")
    if any(a["kind"] == "skeletal_world_root_lock" or
           (a["kind"] == "transform" and (len(a.get("keys", [])) != 1 or a.get("baked_source_curves")
            or a.get("source_behavior_strategy") != "cinetwin_verified_first_frame_static_actor") and not moving)
           for a in actions):
        raise compatibility.CompatibilityError("Retargeted animation has a competing actor or root motion owner.")
    clip_actions = [a for a in actions if a["kind"] == "skeletal_animation"]
    if moving and any(a.get("hold_end_frame") != plan["duration_frames"] + 1 for a in clip_actions):
        raise compatibility.CompatibilityError("Moving character boundary-pose hold differs from the measured frame grid.")
    if any(a.get("expected_root_delta_cm") for a in clip_actions):
        raise compatibility.CompatibilityError("Legacy root delta calibration is unavailable for the approved in-place strategy.")
    rate = plan["display_rate"]
    def frame(seconds):
        return csir_plan.seconds_to_frame(seconds, rate["numerator"], rate["denominator"])
    planned = Counter((a["unreal_asset_path"], a["start_frame"], a["end_frame"],
                       a["source_offset_seconds"], a["time_scale"]) for a in clip_actions)
    expected = Counter((c["planned_target_clip"], frame(c["timing"]["start_seconds"]),
                        frame(c["timing"]["end_seconds"]), c["timing"]["offset_seconds"], c["timing"]["time_scale"])
                       for c in row["clips"])
    if planned != expected:
        raise compatibility.CompatibilityError("Planned clip actions differ from the exact source section inventory.")
    imports = [item for item in manifest["imports"] if item.get("character") == name]
    source = Path(report["context"]["unity_project"])
    for evidence, planned_path in [(row["model"], None), *((c["source"], c["planned_target_clip"]) for c in row["clips"])]:
        path = (source / evidence["asset_path"]).resolve()
        matches = [item for item in imports if ((planned_path is not None and item["kind"] == "AnimSequence"
                    and item["target_asset_path"] == planned_path and item.get("source_animation_path"))
                    or (planned_path is None and item["kind"] == "SkeletalMesh"))]
        if (len(matches) != 1 or Path(matches[0]["source_file"]).resolve() != path
                or matches[0]["source_sha256"] != evidence["sha256"]):
            raise compatibility.CompatibilityError("Staged FBX identity differs from the approved source model or clip.")
    return row


def require_motion_choice(report, choice):
    """Never fall back to dropping a measured moving actor in the AI workflow."""
    if report.get("truncated"):
        raise compatibility.CompatibilityError("Character motion inventory exceeds the bounded compatibility scope.")
    choice = choice if isinstance(choice, dict) else {}
    selected_id = choice.get("source_entity_id") if isinstance(choice, dict) else None
    for row in report["characters"]:
        if row["motion"]["owner"] == "INSUFFICIENT_EVIDENCE":
            raise compatibility.CompatibilityError(f"Character {row['id']} motion refused: {row['motion']['reason']}")
        if row["motion"]["owner"] in (motion.LOCAL_OWNER, "SKELETAL_ROOT", "COMPOUND_OR_UNRESOLVED"):
            if (row["source_entity_id"] != selected_id or choice.get("action_id") != motion.ACTION
                    or row["reasons"]):
                reasons = ", ".join(row["reasons"]) or "Select the registered measured actor trajectory action."
                raise compatibility.CompatibilityError(f"Character {row['id']} motion refused: {reasons}")
