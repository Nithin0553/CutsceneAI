"""Fail-closed release assessment from inspected, source-bound Studio evidence.

This is an independent gate, not the converter or an LLM. A green Unreal
generation alone can never satisfy the source-target fidelity requirements.
Release readiness is a result of independently verified domains, not marketing
labels, local CI, or the number of repair attempts.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class ReleaseEvidenceError(ValueError):
    """The requested job or its evidence is unsafe or not grounded."""


def _read(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ReleaseEvidenceError("Required release evidence does not exist.")
    record = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(record, dict):
        raise ReleaseEvidenceError("Release evidence must be a JSON object.")
    return record


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _latest(candidate: Path, pattern: str, kind: str,
            job: dict[str, Any]) -> dict[str, Any] | None:
    rows = sorted(
        (p for p in candidate.glob(pattern)
         if p.is_file() and p.resolve().parent == candidate),
        key=lambda p: (p.stat().st_mtime_ns, p.name),
        reverse=True,
    )
    if not rows:
        return None
    record = _read(rows[0])
    if record.get("kind") != kind:
        raise ReleaseEvidenceError("Unexpected release-evidence kind: " + rows[0].name)
    for key in ("job_id", "candidate_id"):
        if key in record and record[key] != job[key]:
            raise ReleaseEvidenceError("Release evidence belongs to another " + key)
    return record


def assess(workspace: Path, job_id: str) -> dict[str, Any]:
    root = workspace.resolve()
    if len(job_id) != 32 or any(c not in "0123456789abcdef" for c in job_id):
        raise ReleaseEvidenceError("Invalid Studio job ID.")
    job = _read(root / "jobs" / (job_id + ".json"))
    if job.get("job_id") != job_id or job.get("kind") != "cutsceneai.studio.local_unreal_job":
        raise ReleaseEvidenceError("Job record identity or kind mismatch.")
    candidate_id = str(job.get("candidate_id") or "")
    if (not candidate_id or not candidate_id.isascii() or
            not candidate_id.replace("_", "").isalnum()):
        raise ReleaseEvidenceError("Unsafe candidate ID.")
    candidate = (root / "candidates" / candidate_id).resolve()
    if (candidate != Path(str(job.get("candidate_dir") or "")).resolve()
            or not candidate.is_relative_to((root / "candidates").resolve())):
        raise ReleaseEvidenceError("Candidate path does not match saved job.")

    checks: dict[str, dict[str, Any]] = {}

    def record(name: str, status: str, explanation: str, **numbers: Any) -> None:
        checks[name] = {"status": status, "explanation": explanation, **numbers}

    # Compare current bytes against the PREPARED immutable source/session,
    # not merely the fact that files currently exist at the same path.
    csir_path = Path(str(job.get("csir") or "")).resolve()
    plan_path = candidate / "transfer-plan.json"
    session_path = candidate / "session.json"
    if not csir_path.is_file() or not plan_path.is_file() or not session_path.is_file():
        record("source_and_plan", "INCOMPLETE",
               "Unity CSIR, immutable session and transfer plan must all exist.")
    else:
        plan = _read(plan_path)
        session = _read(session_path)
        source_digest = _sha(csir_path)
        plan_digest = _sha(plan_path)
        matching = (
            session.get("kind") == "cutsceneai.studio.prepared_transfer"
            and session.get("source", {}).get("csir_path") == str(csir_path)
            and session.get("source", {}).get("sha256") == source_digest
            and session.get("target", {}).get("sequence_asset_path") == job.get("sequence_path")
            and session.get("artifact_sha256", {}).get("transfer-plan.json") == plan_digest
            and plan.get("sequence_asset_path") == job.get("sequence_path")
        )
        record(
            "source_and_plan", "PASS" if matching else "FAIL",
            "Source and native target must match the original prepared hashes and sequence.",
            csir_sha256=source_digest, plan_sha256=plan_digest,
        )

    # An LLM strategy is part of conversion only when its exact candidate
    # decision is bound to the submitted job. Synthetic reasoning does not
    # count as a genuine model invocation.
    decision_file = candidate / "ai-conversion-decision.json"
    recorded_decision = job.get("ai_conversion_decision_sha256")
    animation_selected = None
    if not recorded_decision:
        record("ai_pretransfer_planning", "INCOMPLETE",
               "No job-bound AI conversion decision is recorded.")
    elif not decision_file.is_file() or decision_file.is_symlink():
        record("ai_pretransfer_planning", "FAIL",
               "AI decision file is unavailable or unsafe.")
    elif recorded_decision != _sha(decision_file):
        record("ai_pretransfer_planning", "FAIL",
               "AI conversion decision differs from the submitted job bytes.")
    else:
        decision = _read(decision_file)
        animation_selected = decision.get("animation_conversion")
        genuine = bool(
            decision.get("kind") == "cutsceneai.studio.ai_conversion_decision"
            and decision.get("model_invoked") is True
            and decision.get("model_provider") == "OPENAI_RESPONSES"
            and isinstance(decision.get("model_response_id"), str)
            and decision["model_response_id"].startswith("resp_")
        )
        record("ai_pretransfer_planning", "PASS" if genuine else "INCOMPLETE",
               "Genuine source-bound OpenAI planning requires provider response evidence; "
               "mocked selections are insufficient.")
    if animation_selected is None:
        record("ai_native_character_conversion", "NOT_APPLICABLE",
               "No approved AI character retargeting action was selected.")
    else:
        character_file = candidate / "character-native-execution.json"
        char_sha = job.get("character_compatibility_sha256")
        comp_file = candidate / "character-compatibility.json"
        if not character_file.is_file():
            record("ai_native_character_conversion", "INCOMPLETE",
                   "Selected character has no native skeleton/clip readback.")
        elif not comp_file.is_file() or not char_sha or _sha(comp_file) != char_sha:
            record("ai_native_character_conversion", "FAIL",
                   "Character compatibility evidence is missing or modified.")
        else:
            readback = _read(character_file)
            okay = bool(
                readback.get("kind") == "cutsceneai.studio.character_native_readback"
                and readback.get("job_id") == job_id
                and readback.get("source_entity_id") == animation_selected.get("source_entity_id")
                and readback.get("decision_file_sha256") == recorded_decision
                and readback.get("compatibility_file_sha256") == char_sha
                and readback.get("status") == "PASS"
                and job.get("character_native_readback_status") == "PASS"
                and (readback.get("skeleton") or {}).get("status") == "PASS"
                and readback.get("duration_match") is True
                and bool(readback.get("observed_sections"))
                and bool(readback.get("expected_sections"))
                and readback.get("fidelity_verified") is False
            )
            record(
                "ai_native_character_conversion",
                "PASS" if okay else "FAIL",
                "Native retargeting readback must match this exact AI choice, "
                "job, source evidence and clip sections.",
            )

    generation = (
        job.get("generation_status") == "GENERATED_UNVERIFIED"
        and job.get("status") in {
            "GENERATED_AND_MEASURED_NOT_FIDELITY_VERIFIED",
            "GENERATED_DIAGNOSTIC_INCOMPLETE",
        }
    )
    record(
        "native_generation", "PASS" if generation else
        "INCOMPLETE" if job.get("status") in {"QUEUED", "RUNNING"} else "FAIL",
        "Editable Unreal sequence generation; PASS does not imply cinematic fidelity.",
        generated_sequence=job.get("generated_sequence"),
    )

    reopen_audit = _latest(
        candidate, "post-reopen-audit-" + job_id + ".json",
        "cutsceneai.studio.persistence_audit", job,
    )
    generation_audit = _latest(
        candidate, "generation-readback-audit-" + job_id + ".json",
        "cutsceneai.studio.persistence_audit", job,
    )
    persistence = reopen_audit or generation_audit
    if persistence is None:
        record("native_structure_and_save", "INCOMPLETE",
               "Run the native Unreal persistence audit after generation.")
        record("independent_editor_restart", "INCOMPLETE",
               "No independent editor-restart verification evidence exists.")
    else:
        structure = persistence.get("native_structure_status")
        provenance = persistence.get("provenance_status")
        persisted = persistence.get("sequence_persisted") is True
        status = "PASS" if structure == "PASS" and persisted and provenance == "COMPLETE" else (
            "FAIL" if structure == "FAIL" or not persisted else "INCOMPLETE"
        )
        record("native_structure_and_save", status,
               "Saved packages, sequence bindings, mapped actors and provenance readback.",
               assets_verified=persistence.get("assets_class_and_disk_verified"),
               assets_expected=persistence.get("asset_count"),
               actors_verified=persistence.get("actors_unique_and_class_verified"),
               actors_expected=persistence.get("actor_count"))
        # Current audit runs in the open editor. Its explicit restart_verified
        # flag is false until a *distinct process* is independently observed.
        record("independent_editor_restart",
               "PASS" if reopen_audit is not None
               and reopen_audit.get("restart_verified") is True else "INCOMPLETE",
               "A same-editor generation snapshot cannot certify reopen persistence.")

    hierarchy = _latest(
        candidate, "hierarchy-audit-" + job_id + "-*.json",
        "cutsceneai.studio.hierarchy_persistence_audit", job,
    )
    if hierarchy is None:
        record("source_target_hierarchy", "INCOMPLETE",
               "Source-matched native actor attachment audit is missing.")
    else:
        raw = hierarchy.get("status")
        record("source_target_hierarchy",
               "PASS" if raw == "PASS" else "FAIL" if raw == "FAIL" else "INCOMPLETE",
               "Every source parent relation and target actor attachment must be covered.",
               unresolved_source_parents=len(hierarchy.get("unresolved_source_parents") or []),
               incomplete=len(hierarchy.get("incomplete") or []))

    visual = _latest(
        candidate, "visual-audit-" + job_id + "-*.json",
        "cutsceneai.studio.visual_readback_audit", job,
    )
    if visual is None:
        record("native_visual_prerequisites", "INCOMPLETE",
               "Native character materials, camera tracks and environment have not been audited.")
    else:
        issues = list(visual.get("visual_issues") or [])
        environmental_observations = {
            "NO_SKYLIGHT_OR_SKY_ATMOSPHERE_FOUND",
            "NO_DIRECTIONAL_LIGHT_FOUND",
        }
        native_faults = [code for code in issues
                         if code not in environmental_observations]
        directional_required_missing = (
            "NO_DIRECTIONAL_LIGHT_FOUND" in issues
            and visual.get("source_directional_light_required") is True
        )
        # Unity CSIR does not capture all ambient sky/render-pipeline
        # semantics. An absent Unreal SkyLight by itself cannot prove an
        # actual source-to-target transfer defect; it remains INCOMPLETE.
        status = ("FAIL" if native_faults or directional_required_missing
                  else "INCOMPLETE" if issues else "PASS")
        record("native_visual_prerequisites", status,
               "Native faults fail; unmatched source/target environment "
               "observations require source sky/ambient and rendered-frame evidence.",
               findings=issues,
               native_faults=native_faults,
               source_directional_light_required=visual.get(
                   "source_directional_light_required"),
               character_default_slots=visual.get("character_material_slots_engine_default"))

    feedback = _latest(
        candidate, "closed-loop-evaluation-" + job_id + ".json",
        "cutsceneai.studio.closed_loop_evaluation", job,
    )
    if feedback is None:
        record("cinetwin_measured_behavior", "INCOMPLETE",
               "A source-matched CineTwin behavior comparison is unavailable.")
    else:
        measured = feedback.get("cinetwin_measured") is True
        errors = [
            row.get("category") for row in (feedback.get("issues") or [])
            if row.get("category") in {
                "CED_ANIMATION_TRANSFORM_FIDELITY",
                "SOURCE_TARGET_ACTOR_MAPPING",
                "CINETWIN_SOURCE_SAMPLE_COVERAGE",
                "CINETWIN_EVIDENCE_MISSING",
                "CINETWIN_NATIVE_EVALUATION",
            }
        ]
        record("cinetwin_measured_behavior",
               "INCOMPLETE" if not measured else "FAIL" if errors else "PASS",
               "Measured actor/root motion only; other temporal domains require their own tests.",
               motion_or_coverage_issues=errors)

    # Friday's exact CineTwin acceptance lives in an immutable nested folder
    # produced after a *different* Unreal editor process reopens the map.
    # This supplements the legacy closed-loop readback rather than pretending
    # the latest same-editor diagnostic proves saved behavioral parity.
    accepted = [
        p for p in candidate.glob("native-acceptance-*/comparison.json")
        if p.is_file() and not p.is_symlink()
        and p.resolve().parent.parent == candidate
        and p.parent.name.startswith("native-acceptance-")
    ]
    if not accepted:
        record("reopened_temporal_acceptance", "INCOMPLETE",
               "No source-bound post-reopen CineTwin comparison has completed.")
    else:
        chosen = max(accepted, key=lambda p: (p.stat().st_mtime_ns, p.name))
        comparison = _read(chosen)
        folder = chosen.parent
        persistence_file = folder / "persistence.json"
        target_file = folder / "target-behavior.json"
        sampling_file = folder / "sampling-plan.json"
        capture_path = Path(str(job.get("capture") or "")).resolve()
        expected_files = (
            ("persistence_sha256", persistence_file),
            ("target_observation_sha256", target_file),
            ("sampling_plan_sha256", sampling_file),
            ("source_capture_sha256", capture_path),
        )
        if (comparison.get("job_id") != job_id
                or not all(path.is_file() and not path.is_symlink()
                           and comparison.get(key) == _sha(path)
                           for key, path in expected_files)):
            raise ReleaseEvidenceError(
                "Reopened comparison has changed or foreign source/target evidence."
            )
        reopened = _read(persistence_file)
        generation_pid = comparison.get("generation_editor_pid")
        observation_pid = comparison.get("observation_editor_pid")
        same_job = (
            type(generation_pid) is int and generation_pid > 0
            and type(observation_pid) is int and observation_pid > 0
            and generation_pid != observation_pid
            and generation_pid == job.get("generation_editor_pid")
            and reopened.get("kind") == "cutsceneai.studio.persistence_audit"
            and reopened.get("expected_project") == job.get("expected_project")
            and reopened.get("expected_level") == job.get("expected_level")
        )
        if not same_job:
            raise ReleaseEvidenceError(
                "Reopened native measurement has mismatched editor or project identity."
            )
        compared = comparison.get("acceptance_status")
        full_native_scope = bool(
            compared == "STRUCTURE_AND_MEASURED_MOTION_WITHIN_TOLERANCE"
            and reopened.get("restart_verified") is True
            and reopened.get("native_structure_status") == "PASS"
            and reopened.get("provenance_status") == "COMPLETE"
            and reopened.get("status")
            == "STRUCTURAL_READBACK_PASS_DIFFERENT_EDITOR_PROCESS"
        )
        if job.get("character_native_readback_status") == "PASS":
            native_character = comparison.get("character_conversion") or {}
            full_native_scope = full_native_scope and (
                native_character.get("action_id") == "use_approved_ik_retarget_profile"
                and native_character.get("reopened_character_readback_status") == "PASS"
            )
        record(
            "reopened_temporal_acceptance",
            "PASS" if full_native_scope else
            "FAIL" if compared == "DIFFERENCES_DETECTED" else "INCOMPLETE",
            "Distinct-editor native structure and matched-frame actor/root "
            "motion only. Rendering/audio/physics remain separate release domains.",
            native_status=compared,
        )

    for domain, explanation in {
        "rendered_frame_parity": "Matched-time source and target images/camera projections are not independently compared.",
        "full_skeletal_pose": "All animated joint transforms, reference poses and retargeting remain unverified.",
        "audio_and_event_behavior": "Source-matched waveform timing and signal/gameplay side effects remain unverified.",
        "learned_policy_generalization": "No independently approved case-learning improvement on a distinct project is established.",
        "heldout_project_validation": "No held-out Unity source project release evidence is attached.",
    }.items():
        record(domain, "INCOMPLETE", explanation)

    failed = [name for name, item in checks.items() if item["status"] == "FAIL"]
    incomplete = [name for name, item in checks.items() if item["status"] == "INCOMPLETE"]
    return {
        "kind": "cutsceneai.studio.release_readiness",
        "schema_version": "1",
        "job_id": job_id,
        "candidate_id": candidate_id,
        "status": "BLOCKED" if failed else "INCOMPLETE" if incomplete else "READY",
        "release_ready": not failed and not incomplete,
        "checks": checks,
        "failed": failed,
        "incomplete": incomplete,
        "fidelity_verified": False,
        "warning": "A generated editable sequence and green CI cannot certify a release.",
    }
