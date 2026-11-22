"""Fail-closed release assessment from inspected, source-bound Studio evidence.

This is an independent gate, not the converter or an LLM. A green Unreal
generation alone can never satisfy the source-target fidelity requirements.
Release readiness is a result of independently verified domains, not marketing
labels, local CI, or the number of repair attempts.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

# Independent pure-Python comparison replays persisted source/target evidence.
# It never invokes a native engine or treats a synthetic receipt as real data.
_CINETWIN = Path(__file__).resolve().parents[1] / "cinetwin"
if str(_CINETWIN) not in sys.path:
    sys.path.insert(0, str(_CINETWIN))

from behavior_compare import BehavioralComparisonError, compare


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
        openai_recorded = (
            decision.get("model_provider") == "OPENAI_RESPONSES"
            and isinstance(decision.get("model_response_id"), str)
            and decision["model_response_id"].startswith("resp_")
        )
        digest = decision.get("model_response_sha256")
        local_recorded = (
            decision.get("model_provider") == "OLLAMA_LOCAL"
            and isinstance(decision.get("model_name"), str)
            and 0 < len(decision["model_name"]) <= 128
            and isinstance(digest, str) and len(digest) == 64
            and all(ch in "0123456789abcdef" for ch in digest)
        )
        invocation_recorded = bool(
            decision.get("kind") == "cutsceneai.studio.ai_conversion_decision"
            and decision.get("model_invoked") is True
            and (openai_recorded or local_recorded)
        )
        record("ai_pretransfer_planning",
               "PASS" if invocation_recorded else "INCOMPLETE",
               "A job-bound model response was recorded from OpenAI or local "
               "Ollama; injected choices and missing provider evidence are "
               "insufficient. This is not proof of native cinematic fidelity.")
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
            if animation_selected.get("action_id") == "bake_verified_actor_world_trajectory":
                import character_motion
                okay = okay and character_motion.receipt_matches(readback, plan)
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
        record("reopened_camera_optics", "INCOMPLETE",
               "No independent post-reopen physical camera lens observations exist.")
        record("reopened_camera_cut_timing", "INCOMPLETE",
               "No independent post-reopen native camera binding/section readback exists.")
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

        # A comparison JSON is not itself sufficient proof of camera parity.
        # Re-evaluate exact source and observed target bytes whenever a proper
        # source sampling plan requests camera coverage. This detects invented
        # PASS values even when all file SHA-256 references are correct.
        camera_checks = []
        camera_plan = _read(sampling_file)
        if camera_plan.get("kind") == "cinetwin.sampling_plan":
            # The supplied plan and Unity capture must be the immutable inputs
            # of this exact queued candidate, not a self-consistent foreign pair.
            saved_session = _read(session_path)
            captured = saved_session.get("source_capture") or {}
            if (camera_plan.get("source", {}).get("csir_sha256") != _sha(csir_path)
                    or captured.get("path") != str(capture_path)
                    or captured.get("sha256") != _sha(capture_path)):
                raise ReleaseEvidenceError(
                    "Reopened camera evidence does not match the prepared Unity source and capture."
                )
            try:
                recomputed = compare(
                    camera_plan, _read(capture_path), _read(target_file)
                )
            except (BehavioralComparisonError, KeyError, TypeError,
                    ValueError, IndexError, ZeroDivisionError) as exc:
                raise ReleaseEvidenceError(
                    "Camera evidence cannot be recomputed from independent native samples."
                ) from exc
            # Do not accept a plausible-looking comparison JSON with correctly
            # hashed input files but fabricated actor/root/joint measurements.
            for field in ("evaluation", "entities", "rig_motion_diagnostics",
                          "unmapped_source_entities"):
                if comparison.get(field) != recomputed[field]:
                    raise ReleaseEvidenceError(
                        "Reopened behavior metrics differ from source-target samples: " + field
                    )
            if (recomputed["evaluation"]["status"] == "DIFFERENCES_DETECTED"
                    and compared != "DIFFERENCES_DETECTED"):
                raise ReleaseEvidenceError(
                    "Reopened acceptance claimed success despite verified source-target differences."
                )
            for domain, check_name, explanation in (
                ("camera_optics", "reopened_camera_optics",
                 "Sampled native CineCamera sensor height and focal length versus Unity vertical FOV."),
                ("camera_cut_timing", "reopened_camera_cut_timing",
                 "Source-authored cut sections versus native Sequencer camera binding IDs and ranges."),
            ):
                if comparison.get(domain) != recomputed[domain]:
                    raise ReleaseEvidenceError(
                        "Reopened camera comparison differs from measured native evidence: " + domain
                    )
                check_status = recomputed[domain]["status"]
                camera_checks.append(check_status)
                record(check_name, check_status, explanation)
        else:
            record("reopened_camera_optics", "INCOMPLETE",
                   "No valid source sampling-plan contract was attached.")
            record("reopened_camera_cut_timing", "INCOMPLETE",
                   "No valid source sampling-plan contract was attached.")

        full_native_scope = bool(
            compared == "STRUCTURE_AND_MEASURED_MOTION_WITHIN_TOLERANCE"
            and reopened.get("restart_verified") is True
            and reopened.get("native_structure_status") == "PASS"
            and reopened.get("provenance_status") == "COMPLETE"
            and reopened.get("status")
            == "STRUCTURAL_READBACK_PASS_DIFFERENT_EDITOR_PROCESS"
        )
        full_native_scope = full_native_scope and all(
            status in {"PASS", "NOT_APPLICABLE"} for status in camera_checks
        ) and bool(camera_checks)
        if job.get("character_native_readback_status") == "PASS":
            native_character = comparison.get("character_conversion") or {}
            full_native_scope = full_native_scope and (
                native_character.get("action_id") == (animation_selected or {}).get("action_id")
                and native_character.get("action_id") in (
                    "use_approved_ik_retarget_profile", "bake_verified_actor_world_trajectory"
                )
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

    # Element 3 native consent and post-reopen measurement are separate
    # release checks. A native builder receipt is not individual readback,
    # and no measured-domain PASS can establish full cinematic fidelity.
    if (candidate / "element-workflow-active.json").exists():
        tools_path = str(Path(__file__).resolve().parents[2] / "tools")
        if tools_path not in sys.path:
            sys.path.insert(0, tools_path)
        try:
            import studio_element_workflow
            import studio_element_native_execution as native_actions

            permission, manifest = studio_element_workflow.verify_native_job(
                root, job,
            )
            record(
                "element3_native_action_consent", "PASS",
                "Exact registered native actions were separately authorized "
                "for the active source-bound candidate; this is not playback verification.",
                approved_action_count=manifest["action_count"],
                legacy_unattributed_count=manifest["unattributed_count"],
            )
            native_receipt_path = candidate / (
                "unreal-runtime-receipt-" + job_id + ".json"
            )
            dispatch_path = candidate / (
                "element-native-dispatch-" + job_id + ".json"
            )
            if not native_receipt_path.is_file() or not dispatch_path.is_file():
                record(
                    "element3_native_builder_dispatch", "INCOMPLETE",
                    "No completed real Unreal builder receipt and source-bound "
                    "per-action dispatch ledger are both available.",
                )
            else:
                expected_dispatch = native_actions.receipt(
                    permission, manifest, _read(native_receipt_path),
                    job_id=job_id, native_receipt_sha256=_sha(native_receipt_path),
                )
                recorded = _read(dispatch_path)
                if (recorded != expected_dispatch
                        or job.get("element_native_dispatch_status")
                        != "REGISTERED_BUILDER_COMPLETED_INDIVIDUAL_READBACK_UNVERIFIED"
                        or Path(str(job.get("element_native_dispatch_receipt") or "")).resolve()
                        != dispatch_path.resolve()):
                    raise ReleaseEvidenceError(
                        "Element 3 native action dispatch evidence is stale or tampered."
                    )
                record(
                    "element3_native_builder_dispatch", "PASS",
                    "Exact native builder completed registered actions, but individual "
                    "action readback remains unverified.",
                    action_count=expected_dispatch["action_count"],
                )
        except (ValueError, KeyError, TypeError, OSError) as exc:
            record(
                "element3_native_action_consent", "FAIL",
                "Native action consent is missing, changed or refers to a different "
                "candidate: " + type(exc).__name__,
            )
            record(
                "element3_native_builder_dispatch", "FAIL",
                "Cannot accept builder execution without unchanged source-bound consent.",
            )
        if not accepted:
            record(
                "element3_native_reopened_attribution", "INCOMPLETE",
                "No independent different-editor CineTwin target sampling is available.",
            )
        else:
            try:
                import studio_element_workflow
                import studio_element_cinetwin

                snapshot = studio_element_workflow._active(root)
                source_csir = _read(csir_path)
                native_plan = _read(sampling_file)
                source_capture = _read(capture_path)
                observed_target = _read(target_file)
                measured = studio_element_cinetwin.build(
                    source_csir, snapshot["element_plan"], native_plan,
                    source_capture, observed_target,
                )
                if (comparison.get("element3_workflow_sha256")
                        != snapshot["workflow_sha256"]
                        or comparison.get("element3_native_authorization_sha256")
                        != job.get("element_native_authorization_sha256")
                        or comparison.get("element3_source_occurrence_count")
                        != measured["source_occurrence_count"]
                        or measured.get("full_cutscene_fidelity_verified") is not False):
                    raise ReleaseEvidenceError(
                        "Reopened Element 3 provenance does not match the real engine observations."
                    )
                record(
                    "element3_native_reopened_attribution", "PASS",
                    "All source occurrences were independently re-attributed "
                    "from the real reopened native target samples. This is "
                    "measured-scope accounting, not full-cutscene fidelity.",
                    source_occurrence_count=measured["source_occurrence_count"],
                    measured_difference_count=sum(
                        row["measurement_status"] == "DIRECT_MEASURED_DIFFERENCE"
                        for row in measured["occurrences"]
                    ),
                    unmeasured_or_unresolved_count=sum(
                        row["measurement_status"] not in {
                            "DIRECT_MEASURED_NO_FLAGGED_DIFFERENCE",
                            "DIRECT_MEASURED_DIFFERENCE",
                        } for row in measured["occurrences"]
                    ),
                    attribution_sha256=measured["attribution_sha256"],
                    measured_native_fidelity_verified=False,
                )
            except (ValueError, KeyError, TypeError, OSError) as exc:
                record(
                    "element3_native_reopened_attribution", "FAIL",
                    "Source-bound post-reopen CineTwin evidence is altered or incomplete: "
                    + type(exc).__name__,
                )
    else:
        for element_check in (
            "element3_native_action_consent",
            "element3_native_builder_dispatch",
            "element3_native_reopened_attribution",
        ):
            record(
                element_check, "NOT_APPLICABLE",
                "This legacy job did not opt into the new Element 3 workflow.",
            )

    # Element 7 is distinct from the legacy camera/motion acceptance status:
    # it independently reconstructs the complete source-bound CineTwin
    # comparison from persisted raw native capture, checks the exact Element 6
    # one-attempt claim/receipt, and (where available) attributes EVERY source
    # occurrence. Builder completion alone is never a readback PASS.
    if not accepted:
        record(
            "element7_native_execution_chain", "INCOMPLETE",
            "No reopened native observation is available for Element 7.",
        )
        record(
            "element7_cinetwin_recomputation", "INCOMPLETE",
            "No separate source-bound raw-sample verification has completed.",
        )
    else:
        evidence_file = chosen.parent / "element7-readback.json"
        if not evidence_file.exists():
            record(
                "element7_native_execution_chain", "INCOMPLETE",
                "A legacy reopened comparison lacks the new Element 7 "
                "source-bound execution contract.",
            )
            record(
                "element7_cinetwin_recomputation", "INCOMPLETE",
                "Independent Element 7 per-domain and per-occurrence "
                "recomputation is not attached.",
            )
        else:
            try:
                import studio_element7_readback

                proof = _read(evidence_file)
                studio_element7_readback.verify(
                    proof, root, job_id, chosen.parent,
                )
                native_chain = proof["native_attempt"]
                chain_status = (
                    "PASS" if native_chain["status"]
                    == "SOURCE_BOUND_NATIVE_BUILDER_COMPLETED"
                    else "INCOMPLETE"
                )
                measured = proof["measured_scope_status"]
                measured_status = (
                    "FAIL" if measured == "MEASURED_NATIVE_DIFFERENCES_DETECTED"
                    else "PASS" if measured
                    == "MEASURED_NATIVE_SCOPE_WITHIN_TOLERANCE"
                    else "INCOMPLETE"
                )
                record(
                    "element7_native_execution_chain", chain_status,
                    "Exact candidate, Element 6 exclusive attempt and real "
                    "native builder receipt are independently bound. "
                    "Legacy or incomplete attempts remain unverified.",
                    native_attempt_status=native_chain["status"],
                )
                record(
                    "element7_cinetwin_recomputation", measured_status,
                    "Recomputed full-time-grid actor/root/joint/camera "
                    "measurements and optional anonymous per-source attribution. "
                    "No whole-cutscene fidelity or independent engine attestation "
                    "is inferred from stored JSON alone.",
                    measured_scope_status=measured,
                    sampled_frames=proof["sampling_count"],
                    mapped_actors=proof["mapped_entity_count"],
                    unmapped_actors=proof["unmapped_entity_count"],
                    unverified_domains=proof["unverified_domains"],
                    source_occurrence_count=(
                        proof["element_occurrence_attribution"][
                            "source_occurrence_count"
                        ] if proof["element_occurrence_attribution"] else None
                    ),
                    readback_sha256=proof["readback_sha256"],
                )
            except (ValueError, TypeError, KeyError, OSError) as exc:
                record(
                    "element7_native_execution_chain", "FAIL",
                    "Element 7 native execution or receipt evidence was altered: "
                    + type(exc).__name__,
                )
                record(
                    "element7_cinetwin_recomputation", "FAIL",
                    "Element 7 raw CineTwin evidence cannot be independently "
                    "reconstructed from the saved Unity/Unreal samples.",
                )

    # Element 8 never implies a native repair or replay permission. It
    # independently derives a bounded diagnostic from actual source-bound
    # Element 7 files, and refuses to rank an invalid/rehashed comparison.
    if not accepted or not (
        chosen.parent / "element7-readback.json"
    ).is_file():
        record(
            "element8_bounded_repair_triage", "INCOMPLETE",
            "No independently reconstructed post-reopen Element 7 readback "
            "is available for bounded repair triage.",
        )
    else:
        try:
            import studio_element8_repair

            decision = studio_element8_repair.build(
                root, job_id, [chosen.parent],
            )
            existing = candidate / (
                "element8-repair-plan-" + decision["repair_plan_sha256"] + ".json"
            )
            if existing.exists():
                studio_element8_repair.verify(
                    _read(existing), root, job_id, [chosen.parent],
                )
            record(
                "element8_bounded_repair_triage", "PASS",
                "One exact-source native capture was classified using a bounded "
                "read-only strategy policy. This is NOT a native repair grant, "
                "action readback, automatic retry or cinematic fidelity proof.",
                diagnostic_status=decision["status"],
                source_occurrence_count=decision["source_occurrence_count"],
                manual_observation_budget=decision[
                    "remaining_manual_observation_budget"
                ],
                user_authorized_character_offset_review_possible=decision[
                    "native_repair_adapter_available_for_review"
                ],
                native_repair_authorized=False,
                automatic_native_retry_authorized=False,
                repair_plan_sha256=decision["repair_plan_sha256"],
            )
        except (ValueError, KeyError, TypeError, OSError) as exc:
            record(
                "element8_bounded_repair_triage", "FAIL",
                "Element 8 native comparison/repair evidence is missing, "
                "stale or corrupted: " + type(exc).__name__,
            )

    # Element 9 terminates the architectural reasoning loop by accounting for
    # EVERY source occurrence and every unverified domain. A PASS here means
    # only that the limitation report was independently reconstructed; it
    # never promotes measured parity to complete cinematic fidelity.
    try:
        import studio_element9_outcome

        final = studio_element9_outcome.build(root, job_id)
        record(
            "element9_final_outcome_accounting", "PASS",
            "All original source occurrences and required unverified domains "
            "are independently enumerated. Native observation/repair gaps "
            "remain limitations, not successful conversions.",
            final_status=final["status"],
            outcome_sha256=final["outcome_sha256"],
            source_occurrence_count=final["source_occurrence_count"],
            native_observation_count=final["native_observation_count"],
            source_outcome_counts=final["source_outcome_counts"],
            automatic_native_retry_authorized=False,
            full_cutscene_fidelity_verified=False,
        )
    except (ValueError, KeyError, TypeError, OSError) as exc:
        record(
            "element9_final_outcome_accounting", "FAIL",
            "Final source-complete outcome could not be rebuilt from the "
            "candidate, native observations and recovery bounds: "
            + type(exc).__name__,
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
