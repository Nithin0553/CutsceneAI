"""One narrowly scoped, reversible Unreal actor-translation repair.

Never interprets LLM text as coordinates or code. Recomputes full native
CineTwin evidence before and after moving one newly staged skeletal actor.
Will not save unless actor AND root absolute world errors fall below 2 cm.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "packages" / "studio") not in sys.path:
    sys.path.insert(0, str(ROOT / "packages" / "studio"))

import agent_transform_evidence as evidence


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _identical_source(a: dict, b: dict) -> bool:
    fields = ("csir_sha256", "mapping_sha256", "capture_sha256",
              "evaluated_playback_frames")
    return all(a.get(f) == b.get(f) for f in fields)


def attempt(api: Any, workspace: Path, job: dict, request: dict) -> dict:
    candidate = Path(job["candidate_dir"]).resolve()
    original = evidence.source_bound_report(job, candidate)
    target_name = str(request.get("target_entity") or "")
    feedback_id = str(request.get("feedback_id") or "")
    if (len(feedback_id) != 32 or
            any(ch not in "0123456789abcdef" for ch in feedback_id)):
        raise ValueError("An explicit user correction ID is required.")
    pointer = _load(candidate / ("user-feedback-active-" + job["job_id"] + ".json"))
    if (pointer.get("feedback_id") != feedback_id or
            pointer.get("job_id") != job["job_id"] or
            pointer.get("candidate_id") != job["candidate_id"]):
        raise ValueError("Stale user authorization for character translation.")
    feedback = _load(candidate / ("user-feedback-" + feedback_id + ".json"))
    if (feedback.get("kind") != "cutsceneai.studio.user_feedback" or
            feedback.get("feedback_id") != feedback_id or
            feedback.get("job_id") != job["job_id"] or
            feedback.get("candidate_id") != job["candidate_id"] or
            evidence.requested_character_correction(feedback.get("message"), original)
            != target_name):
        raise ValueError("User has not requested this single-character translation.")
    baseline = evidence.review(original, target_name)
    if not baseline.get("eligible"):
        raise ValueError("Original native evidence does not authorize a translation: "
                         + baseline.get("reason", "unknown"))
    if request.get("original_report_sha256") != __import__("hashlib").sha256(
            Path(job["diagnostic_file"]).read_bytes()).hexdigest():
        raise ValueError("Original native diagnostic changed since agent proposal.")
    setup_path = Path(str(job.get("setup_receipt_file") or "")).resolve()
    if setup_path.parent != candidate or not setup_path.is_file():
        raise ValueError("Native actor creation receipt missing.")
    setup = _load(setup_path)
    created = [row for row in setup.get("actors_created", [])
               if row.get("name") == target_name
               and row.get("label") == baseline["target_actor_label"]
               and row.get("kind") == "entity.character"]
    if len(created) != 1:
        raise ValueError("Target is not exactly one newly created character.")

    import diagnose_cinetwin_parity
    def measure() -> dict:
        return diagnose_cinetwin_parity.run(
            csir_path=job["csir"], capture_path=job["capture"],
            mapping_path=job["mapping"], sequence_path=job["sequence_path"],
            output_dir=str(candidate), unreal_api=api,
        )

    fresh = measure()
    if not _identical_source(original["source"], fresh["source"]):
        raise ValueError("Native source evidence changed before repair.")
    if not evidence.same_unreal_project(
            job["expected_project"], fresh["target"].get("project")):
        raise ValueError("Fresh native diagnostic targets a different Unreal project.")
    if not evidence.same_unreal_sequence(
            job["sequence_path"], fresh["target"].get("sequence_path")):
        raise ValueError("Fresh native diagnostic targets a different Level Sequence.")
    plan = evidence.review(fresh, target_name)
    if not plan.get("eligible"):
        raise ValueError("Fresh native re-measurement blocked translation: "
                         + plan.get("reason", "unknown"))
    prior = baseline["offset_source_minus_target_cm"]
    latest = plan["offset_source_minus_target_cm"]
    if math.dist(prior, latest) > 0.1:
        raise ValueError("Actor placement changed since original evidence; no edit.")
    label = plan["target_actor_label"]
    actors = [actor for actor in api.get_editor_subsystem(
        api.EditorActorSubsystem).get_all_level_actors()
        if str(actor.get_actor_label()) == label]
    if len(actors) != 1 or actors[0].get_attach_parent_actor() is not None:
        raise ValueError("New actor label or hierarchy changed before correction.")
    actor = actors[0]
    # Do not silently translate attached props or other descendants.
    all_actors = api.get_editor_subsystem(
        api.EditorActorSubsystem).get_all_level_actors()
    for other in all_actors:
        if other is actor:
            continue
        parent = other.get_attach_parent_actor()
        if parent is not None and str(parent.get_actor_label()) == label:
            raise ValueError("Actor has attached children; translation scope is not isolated.")
    start = actor.get_actor_location()
    first = fresh["frames"][target_name]["actor"][0]["target_cm"]
    old = (float(start.x), float(start.y), float(start.z))
    if math.dist(old, first) > 0.1:
        raise ValueError("Live actor base position differs from evaluated position.")

    offset = plan["offset_source_minus_target_cm"]
    corrected = tuple(a + d for a, d in zip(old, offset))
    changed = False
    saved = False
    try:
        actor.set_actor_location(api.Vector(*corrected), False, True)
        changed = True
        after = measure()
        if not _identical_source(fresh["source"], after["source"]):
            raise ValueError("Source evidence changed during translation.")
        check = evidence.within_tolerance(after, target_name)
        if not check.get("passed"):
            raise ValueError("Post-repair actor/root motion did not meet 2 cm: "
                             + str(check))
        # Sequencer restores the previous editor time after readback; ensure
        # that process did not revert the actor's base location before saving.
        live = actor.get_actor_location()
        live_cm = (float(live.x), float(live.y), float(live.z))
        if math.dist(live_cm, corrected) > 0.1:
            raise ValueError("Sequencer restored a different actor location; do not save.")
        import studio_auto_scene
        studio_auto_scene._save_level(api, job["expected_level"])
        saved = True
        return {
            "status": "TRANSFORM_OFFSET_SAVED_AND_REAUDITED",
            "target_entity": target_name, "changes": 1,
            "offset_applied_cm": offset,
            "actor_error_before_cm": fresh["entities"][target_name]["actor_world"].get(
                "max_absolute_error_cm"),
            "root_error_before_cm": fresh["entities"][target_name]["skeletal_root_world"].get(
                "max_absolute_error_cm"),
            "actor_error_after_cm": check["max_actor_error_cm"],
            "root_error_after_cm": check["max_root_error_cm"],
            "fidelity_verified": False,
            "persistence_after_editor_restart_verified": False,
        }
    finally:
        if changed and not saved:
            # Never leave an unverified placement mutation in the editor.
            actor.set_actor_location(api.Vector(*old), False, True)
