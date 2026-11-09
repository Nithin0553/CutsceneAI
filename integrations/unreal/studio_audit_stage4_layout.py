"""Read-only independent Stage 4 persisted world-pose and parent audit.

Run in the correct Unreal Editor, after Save All AND a fresh project/level reopen.
Never spawns or moves actors, edits packages, creates sequences, or applies mappings.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import ntpath
from pathlib import Path
from typing import Any

POSITION_TOLERANCE_CM = 0.25
ROTATION_TOLERANCE_DEG = 0.15
SCALE_TOLERANCE = 0.005

class Stage4AuditError(RuntimeError):
    pass


def _load(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise Stage4AuditError(f"Expected JSON object: {path}")
    return data


def _sha(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _project_key(value: str) -> str:
    # On Windows, accept both separator styles and casing; no relative guesses.
    return ntpath.normcase(ntpath.normpath(str(value).replace("/", "\\")))


def _angle_error(actual: float, expected: float) -> float:
    # Handles Unreal's -180 <-> +180 angle normalization.
    return abs((actual - expected + 180.0) % 360.0 - 180.0)


def _pose_result(actor: Any, pose: dict) -> dict:
    location = actor.get_actor_location()
    rotation = actor.get_actor_rotation()
    scale = actor.get_actor_scale3d()
    actual_loc = [float(location.x), float(location.y), float(location.z)]
    actual_rot = [float(rotation.roll), float(rotation.pitch), float(rotation.yaw)]
    actual_scale = [float(scale.x), float(scale.y), float(scale.z)]
    expected_loc = [float(x) for x in pose["location_cm"]]
    expected_rot = [float(x) for x in pose["rotation_rpy_degrees"]]
    expected_scale = pose.get("scale_xyz")
    actual_all = actual_loc + actual_rot + actual_scale
    if not all(math.isfinite(x) for x in actual_all):
        return {"pose_matches": False, "reason": "NONFINITE_LIVE_TRANSFORM"}
    pos_delta = [abs(a-b) for a,b in zip(actual_loc, expected_loc)]
    rot_delta = [_angle_error(a,b) for a,b in zip(actual_rot, expected_rot)]
    scale_delta = ([abs(a-float(b)) for a,b in zip(actual_scale, expected_scale)]
                   if expected_scale is not None else None)
    passed = (max(pos_delta) <= POSITION_TOLERANCE_CM and
              max(rot_delta) <= ROTATION_TOLERANCE_DEG and
              (scale_delta is None or max(scale_delta) <= SCALE_TOLERANCE))
    return {
        "pose_matches": passed,
        "expected_location_cm": expected_loc,
        "actual_location_cm": actual_loc,
        "position_abs_error_cm": pos_delta,
        "expected_rotation_rpy_degrees": expected_rot,
        "actual_rotation_rpy_degrees": actual_rot,
        "rotation_abs_error_degrees": rot_delta,
        "expected_scale_xyz": expected_scale,
        "actual_scale_xyz": actual_scale,
        "scale_abs_error": scale_delta,
        "scale_check_skipped": expected_scale is None,
    }


def _mesh_path(actor: Any, api: Any) -> str | None:
    component = actor.get_component_by_class(api.SkeletalMeshComponent)
    if component is None:
        return None
    for field in ("skeletal_mesh_asset", "skeletal_mesh"):
        try:
            value = component.get_editor_property(field)
        except Exception:
            continue
        if value is not None:
            return str(value.get_path_name()).split(".")[0]
    return None


def _check_inputs(plan_path: str, receipt_path: str) -> tuple[dict,dict,dict]:
    plan = _load(plan_path)
    receipt = _load(receipt_path)
    if (plan.get("kind") != "cutsceneai.studio.stage4_source_scene_layout_plan" or
            plan.get("schema_version") != "0.1.0"):
        raise Stage4AuditError("Expected a Stage 4 source scene layout plan")
    if (receipt.get("kind") != "cutsceneai.studio.stage4_source_scene_layout_receipt" or
            receipt.get("status") != "STAGE4_SOURCE_LAYOUT_APPLIED_LEVEL_NOT_SAVED" or
            receipt.get("stage") != "complete"):
        raise Stage4AuditError("Stage 4 receipt is not a completed layout application")
    if _project_key(receipt.get("plan_path", "")) != _project_key(str(plan_path)):
        raise Stage4AuditError("Stage 4 receipt does not belong to this plan")
    if (receipt.get("verified_level") != plan.get("target_level") or
            _project_key(receipt.get("verified_project", "")) != _project_key(plan.get("target_project", ""))):
        raise Stage4AuditError("Stage 4 receipt project/level differs from plan")
    for path_key, digest_key in (
        ("source_csir_path", "source_csir_sha256"),
        ("stage3_plan_path", "stage3_plan_sha256"),
        ("stage3_receipt_path", "stage3_receipt_sha256"),
        ("stage3_audit_path", "stage3_audit_sha256"),
        ("mapping_path", "mapping_sha256"),
    ):
        try:
            if _sha(plan[path_key]) != plan[digest_key]:
                raise Stage4AuditError(f"Stage 4 evidence changed: {path_key}")
        except OSError as error:
            raise Stage4AuditError(f"Stage 4 evidence unavailable: {path_key}: {error}") from error
    stage3 = _load(plan["stage3_plan_path"])
    if stage3.get("kind") != "cutsceneai.studio.stage3_scene_plan":
        raise Stage4AuditError("Invalid Stage 3 plan provenance")
    actors = stage3.get("actors", [])
    placements = plan.get("placements", [])
    expected_names = {row["source_name"] for row in actors}
    expected_labels = {row["actor_label"] for row in actors}
    if (len(actors) != 8 or len(expected_names) != 8 or len(expected_labels) != 8 or
            len(placements) != 8 or {p["entity_name"] for p in placements} != expected_names or
            {p["actor_label"] for p in placements} != expected_labels or
            plan.get("missing_source_poses") or plan.get("hierarchy_blocker") is not None):
        raise Stage4AuditError("Incomplete/ambiguous eight-actor layout plan")
    if {x["entity_name"] for x in receipt.get("placements_applied", [])} != expected_names or len(receipt.get("placements_applied", [])) != 8:
        raise Stage4AuditError("Stage 4 receipt does not list all eight placements")
    expected_edges = {(e["entity_name"], e["source_parent_name"])
                      for e in plan.get("hierarchy", {}).get("attachments", [])}
    applied_edges = {(e["entity_name"], e["parent_name"])
                     for e in receipt.get("attachments_applied", [])}
    if expected_edges != applied_edges or len(receipt.get("attachments_applied", [])) != len(expected_edges):
        raise Stage4AuditError("Stage 4 attachment receipt differs from plan")
    if (plan.get("target_project") != stage3.get("target_project") or
            plan.get("target_level") != stage3.get("target_level")):
        raise Stage4AuditError("Stage 3/4 target mismatch")
    return plan, receipt, stage3


def run(plan_path: str, receipt_path: str, *, unreal_api: Any = None) -> dict:
    api = unreal_api
    if api is None:
        import unreal as api
    plan, _receipt, stage3 = _check_inputs(plan_path, receipt_path)

    raw_project = str(api.Paths.get_project_file_path())
    full = getattr(api.Paths, "convert_relative_path_to_full", None)
    live_project = str(full(raw_project)) if callable(full) else raw_project
    if _project_key(live_project) != _project_key(plan["target_project"]):
        raise Stage4AuditError("Wrong Unreal project: " + live_project)
    world = api.get_editor_subsystem(api.UnrealEditorSubsystem).get_editor_world()
    live_level = str(world.get_path_name()).split(".")[0]
    if live_level != plan["target_level"]:
        raise Stage4AuditError("Wrong Unreal level: " + live_level)

    level_file = (Path(plan["target_project"]).parent / "Content" /
                  (plan["target_level"][len("/Game/"):] + ".umap"))
    saved_level_file_exists = level_file.is_file()

    live_actors = api.get_editor_subsystem(api.EditorActorSubsystem).get_all_level_actors()
    by_label: dict[str, list[Any]] = {}
    for actor in live_actors:
        by_label.setdefault(str(actor.get_actor_label()), []).append(actor)
    pose_by_name = {p["entity_name"]: p for p in plan["placements"]}
    labels_by_name = {row["source_name"]: row["actor_label"] for row in stage3["actors"]}
    expected_parent = {e["entity_name"]: e["source_parent_name"]
                       for e in plan["hierarchy"].get("attachments", [])}
    rows = []
    for entry in stage3["actors"]:
        name, label = entry["source_name"], entry["actor_label"]
        matching = by_label.get(label, [])
        row = {"source_name": name, "actor_label": label, "actor_count": len(matching),
               "class_matches": False, "mesh_matches": None, "parent_matches": False,
               "pose_matches": False, "readback_ready": False}
        if len(matching) == 1:
            actor = matching[0]
            expected_class = {"character": "SkeletalMeshActor", "camera": "CineCameraActor",
                              "light": "PointLight", "prop": "Actor"}[entry["kind"]]
            actual_class = str(actor.get_class().get_name())
            row["class_name"] = actual_class
            row["class_matches"] = actual_class == expected_class
            if entry["kind"] == "character":
                actual_mesh = _mesh_path(actor, api)
                row["actual_mesh_path"] = actual_mesh
                row["mesh_matches"] = actual_mesh == entry["mesh_path"]
            parent = actor.get_attach_parent_actor()
            actual_parent_label = str(parent.get_actor_label()) if parent is not None else None
            required_parent = labels_by_name[expected_parent[name]] if name in expected_parent else None
            row["actual_parent_label"] = actual_parent_label
            row["expected_parent_label"] = required_parent
            row["parent_matches"] = actual_parent_label == required_parent
            row.update(_pose_result(actor, pose_by_name[name]))
            row["readback_ready"] = (row["class_matches"] and
                                     row["mesh_matches"] is not False and
                                     row["parent_matches"] and row["pose_matches"])
        rows.append(row)
    all_readback = all(row["readback_ready"] for row in rows)
    passed = all_readback and saved_level_file_exists
    result = {
        "kind": "cutsceneai.studio.stage4_layout_persistence_audit",
        "schema_version": "0.1.0",
        "status": "STAGE4_SAVED_LAYOUT_READBACK" if passed else "STAGE4_LAYOUT_READBACK_INCOMPLETE",
        "project": live_project, "level": live_level,
        "plan_path": str(Path(plan_path)), "receipt_path": str(Path(receipt_path)),
        "readback_count": sum(bool(row["readback_ready"]) for row in rows),
        "expected_count": len(rows), "saved_level_file_exists": saved_level_file_exists,
        "saved_level_file_path": str(level_file),
        "attachments_verified": sum(bool(row["parent_matches"]) for row in rows if row["source_name"] in expected_parent),
        "attachments_expected": len(expected_parent),
        "thresholds": {"position_cm": POSITION_TOLERANCE_CM,
                       "rotation_degrees": ROTATION_TOLERANCE_DEG, "scale": SCALE_TOLERANCE},
        "rows": rows,
        "notes": ["Audit is read-only; verifies current loaded scene and on-disk level package.",
                  "Reopen project and level after Save All for a persistence check.",
                  "Scene source/target playback fidelity is NOT verified.",
                  "No Level Sequence or visual/material/audio comparison performed."],
        "fidelity_verified": False, "sequence_generated": False,
    }
    output = Path(receipt_path).with_name(
        "stage4_persistence_audit_" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    with output.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    api.log("[CutSceneAI] STAGE 4 READBACK: " + result["status"])
    api.log(f"[CutSceneAI] ACTORS: {result['readback_count']}/{result['expected_count']} ATTACHMENTS: {result['attachments_verified']}/{result['attachments_expected']}")
    api.log("[CutSceneAI] REPORT: " + str(output))
    api.log("[CutSceneAI] NOT A SOURCE/TARGET CUTSCENE FIDELITY PASS")
    return result
