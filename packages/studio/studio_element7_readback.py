"""Element 7: independently reproducible, source-bound native CineTwin readback.

This module runs *after* a real reopened-editor observer has written native
persistence, sampling, target capture and comparison files. It only reads
immutable candidate/observation evidence and replays the existing CineTwin
comparator. A valid JSON file is not cryptographic proof that an engine ran.

Its report intentionally does NOT declare whole-cutscene fidelity, authorize
repairs, or permit another native execution attempt.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
CINETWIN = str(HERE.parent / "cinetwin")
if CINETWIN not in sys.path:
    sys.path.insert(0, CINETWIN)

import studio_element5_plan as source_plan
import studio_element6_execution as native_guard
import studio_element_cinetwin
import studio_element_native_execution as native_actions
from behavior_compare import BehavioralComparisonError, compare
from sampling_plan import SamplingPlanError, build_plan, validate_capture
from target_observation_plan import TargetPlanError, prepare_observation

KIND = "cutsceneai.studio.element7_native_cinetwin_readback"
VERSION = "1"
JOB_ID = re.compile(r"[a-f0-9]{32}\Z")
CANDIDATE = re.compile(r"[0-9]{8}T[0-9]{6}Z_[a-f0-9]{8}\Z")
MAX_BYTES = 128 * 1024 * 1024
class Element7ReadbackError(ValueError):
    """Target/source/native evidence is missing, foreign, stale or untrusted."""


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _safe_json(path: Path) -> tuple[dict, str]:
    if (path.is_symlink() or not path.is_file()
            or not 0 < path.stat().st_size <= MAX_BYTES):
        raise Element7ReadbackError("Native CineTwin evidence is missing or unsafe.")
    data = path.read_bytes()
    try:
        document = json.loads(data.decode("utf-8-sig"))
    except (UnicodeError, ValueError) as exc:
        raise Element7ReadbackError("Native CineTwin evidence is malformed.") from exc
    if not isinstance(document, dict):
        raise Element7ReadbackError("Native CineTwin evidence must be a JSON object.")
    return document, hashlib.sha256(data).hexdigest()


def _bound_paths(workspace: Path, job_id: str, folder: Path):
    if not isinstance(job_id, str) or not JOB_ID.fullmatch(job_id):
        raise Element7ReadbackError("Invalid native readback job identity.")
    root = Path(workspace).resolve()
    if (root / "jobs").is_symlink():
        raise Element7ReadbackError("Native job directory is unsafe.")
    job, _ = _safe_json(root / "jobs" / (job_id + ".json"))
    candidate_id = job.get("candidate_id")
    if (job.get("kind") != "cutsceneai.studio.local_unreal_job"
            or job.get("job_id") != job_id
            or not isinstance(candidate_id, str)
            or not CANDIDATE.fullmatch(candidate_id)):
        raise Element7ReadbackError("Native readback belongs to another job.")
    candidate_root = root / "candidates"
    if candidate_root.is_symlink():
        raise Element7ReadbackError("Candidate directory is unsafe.")
    candidate = candidate_root / candidate_id
    if (candidate.is_symlink() or not candidate.is_dir()
            or candidate.resolve().parent != candidate_root.resolve()
            or candidate.resolve() != Path(str(job.get("candidate_dir") or "")).resolve()):
        raise Element7ReadbackError("Reopened native evidence has a foreign candidate.")
    observation = Path(folder)
    if (observation.is_symlink() or not observation.is_dir()
            or observation.resolve().parent != candidate.resolve()
            or not observation.name.startswith("native-acceptance-")):
        raise Element7ReadbackError("Native readback folder is not candidate-local.")
    return root, candidate, observation, job


def _attempt(root: Path, candidate: Path, job: dict) -> dict:
    """No fallback from incomplete or forged native claims to a legacy PASS."""
    jid = job["job_id"]
    claim_file = candidate / ("element6-native-claim-" + jid + ".json")
    if not claim_file.exists():
        return {
            "status": "LEGACY_NATIVE_ATTEMPT_UNVERIFIED",
            "native_builder_completed": False,
            "claim_sha256": None, "runtime_receipt_sha256": None,
            "native_execution_replay_allowed": False,
        }
    claim, _ = _safe_json(claim_file)
    try:
        state = native_guard.inspect(root, job)
        expected_fingerprints = native_guard._fingerprints(candidate, job)
        if (claim.get("kind") != native_guard.KIND
                or claim.get("claim_sha256") != native_guard.digest({
                    k: v for k, v in claim.items() if k != "claim_sha256"
                })
                or claim.get("immutable_job_identity_sha256")
                != native_guard.digest(native_guard._identity(job))
                or claim.get("source_and_prepared_evidence")
                != expected_fingerprints
                or claim.get("editor_pid") != job.get("generation_editor_pid")
                or claim.get("native_attempt_index") != 1
                or claim.get("claim_scope")
                != "SINGLE_ENGINE_ATTEMPT_NO_AUTOMATIC_REPLAY"
                or state.get("native_replay_allowed") is not False):
            raise Element7ReadbackError(
                "Reopened readback cannot be tied to the original native execution."
            )
        receipt_file = candidate / ("element6-native-receipt-" + jid + ".json")
        if not receipt_file.exists():
            return {
                "status": "INCOMPLETE_NATIVE_EXECUTION_RECEIPT",
                "native_builder_completed": False,
                "claim_sha256": claim["claim_sha256"],
                "runtime_receipt_sha256": None,
                "native_execution_replay_allowed": False,
            }
        receipt, _ = _safe_json(receipt_file)
        runtime_file = candidate / ("unreal-runtime-receipt-" + jid + ".json")
        runtime, runtime_sha = _safe_json(runtime_file)
        completed = (
            job.get("generation_status") == "GENERATED_UNVERIFIED"
            and job.get("status") in {
                "GENERATED_AND_MEASURED_NOT_FIDELITY_VERIFIED",
                "GENERATED_DIAGNOSTIC_INCOMPLETE",
            }
            and state["status"]
            == "NATIVE_BUILDER_COMPLETED_READBACK_AND_FIDELITY_UNVERIFIED"
            and state["stages"] == list(native_guard.STAGES[1:])
            and receipt["runtime_receipt_sha256"] == runtime_sha
            and receipt["status"] == state["status"]
            and receipt.get("native_builder_completed") is True
            and receipt.get("individual_native_action_readbacks_verified") is False
            and receipt.get("full_cutscene_fidelity_verified") is False
            and runtime.get("kind") == "cutsceneai.unreal.best_effort_receipt"
            and runtime.get("status") == "GENERATED_UNVERIFIED"
            and runtime.get("stage") == "complete"
            and runtime.get("transfer_plan_sha256")
            == expected_fingerprints["prepared_plan_file_sha256"]
        )
        if receipt.get("runtime_receipt_sha256") != runtime_sha:
            raise Element7ReadbackError("Native builder receipt bytes changed after execution.")
        return {
            "status": (
                "SOURCE_BOUND_NATIVE_BUILDER_COMPLETED"
                if completed else "NATIVE_EXECUTION_INCOMPLETE_MUST_INSPECT"
            ),
            "native_builder_completed": completed,
            "claim_sha256": claim["claim_sha256"],
            "runtime_receipt_sha256": runtime_sha,
            "native_execution_replay_allowed": False,
        }
    except (native_guard.GuardedExecutionError, KeyError, TypeError) as exc:
        raise Element7ReadbackError(
            "Element 6 native attempt records are altered or incomplete."
        ) from exc


def build(workspace: Path, job_id: str, evidence_folder: Path) -> dict[str, Any]:
    """Recompute from persisted source, exact native samples and execution chain."""
    root, candidate, folder, job = _bound_paths(workspace, job_id, evidence_folder)
    session, session_sha = _safe_json(candidate / "session.json")
    csir_path = Path(str(job.get("csir") or ""))
    mapping_path = Path(str(job.get("mapping") or ""))
    csir, csir_sha = _safe_json(csir_path)
    mapping, mapping_sha = _safe_json(mapping_path)
    transfer, transfer_sha = _safe_json(candidate / "transfer-plan.json")
    source_path = Path(str(job.get("capture") or ""))
    source, source_sha = _safe_json(source_path)
    sampling, sampling_sha = _safe_json(folder / "sampling-plan.json")
    target, target_sha = _safe_json(folder / "target-behavior.json")
    persistence, persistence_sha = _safe_json(folder / "persistence.json")
    recorded, recorded_sha = _safe_json(folder / "comparison.json")
    if (session.get("kind") != "cutsceneai.studio.prepared_transfer"
            or session.get("source", {}).get("csir_path") != str(csir_path)
            or session.get("source", {}).get("sha256") != csir_sha
            or (session.get("source_capture") or {}).get("path") != str(source_path)
            or (session.get("source_capture") or {}).get("sha256") != source_sha
            or session.get("target", {}).get("mapping_path") != str(mapping_path)
            or session.get("target", {}).get("sequence_asset_path")
            != job.get("sequence_path")
            or session.get("artifact_sha256", {}).get("transfer-plan.json")
            != transfer_sha
            or transfer.get("sequence_asset_path") != job.get("sequence_path")
            or mapping.get("sequence_asset_path") != job.get("sequence_path")):
        raise Element7ReadbackError(
            "Reopened native evidence differs from the immutable source/target candidate."
        )
    try:
        expected_sampling = build_plan(csir, csir_sha256=csir_sha)
        if sampling != expected_sampling:
            raise Element7ReadbackError(
                "Reopened CineTwin sampling plan differs from the exact Unity CSIR."
            )
        src_validation = validate_capture(sampling, source)
        if src_validation.get("failures"):
            raise Element7ReadbackError(
                "Unity source capture has incomplete or incorrect sample coverage."
            )
        expected_targets = prepare_observation(sampling, mapping)
        exact_bindings = {
            row["entity_id"]: row["actor_label"]
            for row in expected_targets["bound"]
        }
        native_rows = (target.get("samples") or [{}])[0].get("entities", [])
        observed_bindings = {
            row["entity_id"]: row.get("actor_label")
            for row in native_rows
        }
        expected_missing = {
            row["entity_id"] for row in expected_targets["missing"]
        }
        observed_missing = {
            row["entity_id"] for row in target.get(
                "coverage", {},
            ).get("unmapped_source_entities", [])
        }
        if (observed_bindings != exact_bindings
                or expected_missing != observed_missing
                or target.get("skeletal_bone_maps", {})
                != expected_targets["skeletal_bone_maps"]
                or target.get("coverage", {}).get("mapped_entity_count")
                != len(exact_bindings)
                or target.get("coverage", {}).get("source_entity_count")
                != len(sampling["entities"])):
            raise Element7ReadbackError(
                "Native sampled actor labels and rigs differ from the exact "
                "prepared target mapping; no inferred source match is allowed."
            )
        extras: dict[str, Any] = {}
        optional = (
            ("rig_calibration_sha256", "rig-calibration.json", "pose_calibration"),
            ("mesh_forward_approval_sha256", "mesh-forward-approval.json",
             "mesh_forward_approval"),
        )
        for sha_field, name, key in optional:
            if recorded.get(sha_field) is not None:
                document, doc_sha = _safe_json(folder / name)
                if recorded[sha_field] != doc_sha:
                    raise Element7ReadbackError(
                        "Native CineTwin calibrated pose/forward evidence was replaced."
                    )
                extras[key] = document
            elif (folder / name).exists():
                raise Element7ReadbackError(
                    "Unreferenced native pose/forward evidence is not allowed."
                )
        computed = compare(sampling, source, target, **extras)
    except Element7ReadbackError:
        # Preserve the specific, bounded integrity diagnostic for an
        # intentionally rejected source/mapping/approval mismatch.
        raise
    except (SamplingPlanError, TargetPlanError, BehavioralComparisonError,
            ValueError, IndexError, TypeError, KeyError, ZeroDivisionError) as exc:
        raise Element7ReadbackError(
            "Native CineTwin source/target comparison could not be reconstructed."
        ) from exc
    for key in (
        "kind", "evaluation", "entities", "rig_motion_diagnostics",
        "camera_optics", "camera_cut_timing",
        "unmapped_source_entities", "unverified_domains",
    ):
        if recorded.get(key) != computed.get(key):
            raise Element7ReadbackError(
                "Persisted native comparison disagrees with independently measured "
                "source and target observations: " + key
            )
    expected_recorded = {
        "job_id": job_id, "source_capture_sha256": source_sha,
        "sampling_plan_sha256": sampling_sha,
        "target_observation_sha256": target_sha,
        "persistence_sha256": persistence_sha,
        "generation_editor_pid": job.get("generation_editor_pid"),
    }
    if (any(recorded.get(k) != v for k, v in expected_recorded.items())
            or recorded.get("native_persistence_status")
            != persistence.get("status")
            or recorded.get("full_cutscene_fidelity_verified") is not False):
        raise Element7ReadbackError(
            "Native readback comparison has a foreign input, stale persistence, "
            "invalid editor identity or unsupported fidelity claim."
        )
    target_info = target.get("target") or {}
    generation_pid = job.get("generation_editor_pid")
    observation_pid = target_info.get("editor_pid")
    if (type(generation_pid) is not int or generation_pid <= 0
            or type(observation_pid) is not int or observation_pid <= 0
            or generation_pid == observation_pid
            or recorded.get("observation_editor_pid") != observation_pid
            or target_info.get("sequence_asset_path", "").split(".", 1)[0]
            != job.get("sequence_path")):
        raise Element7ReadbackError(
            "Reopened native observation lacks a distinct matching editor process."
        )
    project_file = Path(str(job.get("expected_project") or ""))
    if (project_file.is_symlink() or not project_file.is_file()
            or not 0 < project_file.stat().st_size <= 4 * 1024 * 1024):
        raise Element7ReadbackError(
            "The reopened Unreal project identity cannot be verified."
        )
    project_bytes = project_file.read_bytes()
    project_sha = hashlib.sha256(project_bytes).hexdigest()
    identity = hashlib.sha256(
        str(project_file.resolve()).encode("utf-8")
        + b"\x00" + project_bytes
    ).hexdigest()
    if (target_info.get("engine") != "unreal"
            or target_info.get("project_file_sha256") != project_sha
            or target_info.get("project_identity_sha256") != identity
            or persistence.get("expected_project") != job["expected_project"]
            or persistence.get("expected_level") != job.get("expected_level")
            or persistence.get("kind")
            != "cutsceneai.studio.persistence_audit"):
        raise Element7ReadbackError(
            "Measured target is not the reopened prepared Unreal project/level."
        )
    # Reproduce native acceptance's measured-scope classification, rather
    # than trusting a comparison.json "PASS" label with newly calculated
    # hashes. Valid JSON documents alone cannot attest actual engine origin.
    joint_statuses = [
        row["joint_positions"].get("status")
        for row in computed["rig_motion_diagnostics"]
    ]
    calibrated = [
        row["joint_reference_orientation"].get("status")
        for row in computed["rig_motion_diagnostics"]
    ]
    forward = [
        row["anatomical_mesh_forward"].get("status")
        for row in computed["rig_motion_diagnostics"]
    ]
    character = recorded.get("character_conversion") or {}
    character_status = (
        character.get("reopened_character_readback_status")
        if job.get("character_native_readback_status") == "PASS" else "PASS"
    )
    if (computed["evaluation"]["status"] == "DIFFERENCES_DETECTED"
            or persistence.get("native_structure_status") == "FAIL"
            or character_status == "FAIL"
            or computed["camera_optics"]["status"] == "FAIL"
            or computed["camera_cut_timing"]["status"] == "FAIL"):
        expected_status = "DIFFERENCES_DETECTED"
    elif (persistence.get("restart_verified") is not True
          or computed["evaluation"]["unmapped_entity_count"]
          or "INCOMPLETE" in joint_statuses
          or ("pose_calibration" in extras
              and (not calibrated or "INCOMPLETE" in calibrated))
          or ("mesh_forward_approval" in extras
              and (not forward or "INCOMPLETE" in forward))
          or (target.get("quality") or {}).get("status") == "SUSPECT"
          or character_status != "PASS"
          or computed["camera_optics"]["status"] == "INCOMPLETE"
          or computed["camera_cut_timing"]["status"] == "INCOMPLETE"):
        expected_status = "INCOMPLETE_MEASURED_SCOPE"
    else:
        expected_status = "STRUCTURE_AND_MEASURED_MOTION_WITHIN_TOLERANCE"
    if recorded.get("acceptance_status") != expected_status:
        raise Element7ReadbackError(
            "Native acceptance status differs from the independently "
            "recomputed source/target/native measurements."
        )
    quality = target.get("quality") or {}
    tick_observed = (
        quality.get("method") == "slate_post_tick_between_sequencer_seeks"
        and type(quality.get("ticks_per_sample")) is int
        and quality["ticks_per_sample"] >= 2
        and quality.get("status") == "OBSERVED_NOT_YET_PROVEN"
        and target.get("coverage", {}).get("full_temporal_coverage") is True
    )
    attempt = _attempt(root, candidate, job)
    attributed = None
    pointer_path = candidate / "element-workflow-active.json"
    if pointer_path.exists():
        pointer, _ = _safe_json(pointer_path)
        digest = pointer.get("workflow_sha256")
        if (not isinstance(digest, str)
                or not re.fullmatch(r"[a-f0-9]{64}", digest)
                or pointer.get("candidate_id") != job.get("candidate_id")):
            raise Element7ReadbackError("Current Element 3 review identity is invalid.")
        snapshot, _ = _safe_json(candidate / ("element-workflow-" + digest + ".json"))
        if (snapshot.get("workflow_sha256") != digest
                or snapshot.get("kind") != "cutsceneai.studio.element_workflow"
                or snapshot.get("candidate_id") != job["candidate_id"]
                or digest != _hash({
                    key: value for key, value in snapshot.items()
                    if key != "workflow_sha256"
                })
                or snapshot.get("source_file_sha256") != csir_sha
                or snapshot.get("candidate_mapping_sha256") != mapping_sha
                or snapshot.get("transfer_plan_sha256") != transfer_sha
                or snapshot.get("target_project_identity_sha256")
                != hashlib.sha256(str(project_file.resolve()).encode(
                    "utf-8"
                )).hexdigest()
                or recorded.get("element3_workflow_sha256") != digest
                or recorded.get("element3_native_authorization_sha256")
                != job.get("element_native_authorization_sha256")):
            raise Element7ReadbackError(
                "Measured target uses an unapproved/foreign source occurrence plan."
            )
        # Re-evaluate the saved Element 3/4/5 decisions and EXACT native
        # operator grant without importing Unreal or trusting editor UI.
        try:
            source_plan.verify(
                snapshot["element5_source_bound_plan"],
                csir, mapping, transfer, snapshot["element_plan"],
                snapshot["element_schedule"], snapshot["element_strategy"],
                snapshot["element4_baseline_validation"],
            )
            manifest = native_actions.inventory(
                transfer, snapshot["element_plan"], snapshot["element_strategy"],
            )
            approval, _ = _safe_json(
                candidate / "element-native-approval.json"
            )
            native_actions.verify_authorization(
                approval, manifest, candidate_id=job["candidate_id"],
                workflow_sha256=digest,
                transfer_plan_sha256=transfer_sha,
            )
            if (approval["authorization_sha256"]
                    != job.get("element_native_authorization_sha256")):
                raise Element7ReadbackError(
                    "Native target observation does not belong to approved actions."
                )
        except (source_plan.SourceBoundPlanError,
                native_actions.ElementNativeExecutionError,
                Element7ReadbackError, KeyError, TypeError, ValueError) as exc:
            raise Element7ReadbackError(
                "Element 7 source/action provenance or operator consent is invalid."
            ) from exc
        try:
            attribution = studio_element_cinetwin.build(
                csir, snapshot["element_plan"], sampling, source, target,
            )
        except (studio_element_cinetwin.ElementCineTwinError,
                KeyError, ValueError, TypeError) as exc:
            raise Element7ReadbackError(
                "Exact-source CineTwin occurrence attribution cannot be reproduced."
            ) from exc
        if recorded.get("element3_source_occurrence_count") != attribution[
            "source_occurrence_count"
        ]:
            raise Element7ReadbackError(
                "Native readback omitted source assets, tracks or relationships."
            )
        attributed = {
            "workflow_sha256": digest,
            "attribution_sha256": attribution["attribution_sha256"],
            "source_occurrence_count": attribution["source_occurrence_count"],
            "measurement_state_counts": dict(sorted(Counter(
                row["measurement_status"] for row in attribution["occurrences"]
            ).items())),
            "per_occurrence": [{
                "occurrence_id": row["occurrence_id"],
                "source_kind": row["source_kind"],
                "measurement_status": row["measurement_status"],
                "discrepancy_flags": list(row["discrepancy_flags"]),
            } for row in attribution["occurrences"]],
        }
    discrepancies = (
        computed["evaluation"]["status"] == "DIFFERENCES_DETECTED"
        or any(row["joint_positions"].get("status") == "FAIL"
               for row in computed["rig_motion_diagnostics"])
        or computed["camera_optics"]["status"] == "FAIL"
        or computed["camera_cut_timing"]["status"] == "FAIL"
        or persistence.get("native_structure_status") == "FAIL"
    )
    if discrepancies:
        status = "MEASURED_NATIVE_DIFFERENCES_DETECTED"
    elif (not tick_observed
            or persistence.get("restart_verified") is not True
            or persistence.get("native_structure_status") != "PASS"
            or persistence.get("sequence_persisted") is not True
            or persistence.get("provenance_status") != "COMPLETE"
            or persistence.get("status")
            != "STRUCTURAL_READBACK_PASS_DIFFERENT_EDITOR_PROCESS"
            or computed["evaluation"]["unmapped_entity_count"] != 0
            or any(row["joint_positions"].get("status") != "PASS"
                   for row in computed["rig_motion_diagnostics"])
            or computed["camera_optics"]["status"] not in ("PASS", "NOT_APPLICABLE")
            or computed["camera_cut_timing"]["status"] not in ("PASS", "NOT_APPLICABLE")
            or attempt["status"] != "SOURCE_BOUND_NATIVE_BUILDER_COMPLETED"):
        status = "NATIVE_MEASURED_SCOPE_INCOMPLETE"
    else:
        status = "MEASURED_NATIVE_SCOPE_WITHIN_TOLERANCE"
    report = {
        "kind": KIND, "schema_version": VERSION,
        "job_id_sha256": _hash(job_id),
        "candidate_id_sha256": _hash(job["candidate_id"]),
        "sequence_identity_sha256": _hash(job["sequence_path"]),
        "source_csir_file_sha256": csir_sha,
        "source_capture_file_sha256": source_sha,
        "prepared_session_file_sha256": session_sha,
        "prepared_plan_file_sha256": transfer_sha,
        "target_mapping_file_sha256": mapping_sha,
        "source_target_mapping_status": "EXACT_PREPARED_MAPPING_OBSERVED",
        "sampling_file_sha256": sampling_sha,
        "target_capture_file_sha256": target_sha,
        "native_persistence_file_sha256": persistence_sha,
        "native_comparison_file_sha256": recorded_sha,
        "recomputed_cinetwin_sha256": _hash(computed),
        "generation_editor_process_sha256": _hash(generation_pid),
        "observation_editor_process_sha256": _hash(observation_pid),
        "distinct_reopened_editor_observed": True,
        "native_persistence_status": persistence.get("status"),
        "native_structure_status": persistence.get("native_structure_status"),
        "target_tick_sampling_status": (
            "TICK_SYNCHRONIZED_FULL_GRID_CLAIMED"
            if tick_observed else "NATIVE_TICK_EVIDENCE_INCOMPLETE"
        ),
        "mapped_entity_count": computed["evaluation"]["mapped_actor_count"],
        "source_entity_count": computed["evaluation"]["source_entity_count"],
        "unmapped_entity_count": computed["evaluation"]["unmapped_entity_count"],
        "sampling_count": computed["evaluation"]["sampling_times"],
        "camera_lens_status": computed["camera_optics"]["status"],
        "camera_cuts_status": computed["camera_cut_timing"]["status"],
        "native_attempt": attempt,
        "element_occurrence_attribution": attributed,
        "measured_scope_status": status,
        "unverified_domains": sorted(set(computed["unverified_domains"])),
        "native_readback_is_self_reported_engine_evidence": True,
        "independent_engine_attestation_verified": False,
        "native_repair_authorized": False,
        "native_retry_authorized": False,
        "full_cutscene_fidelity_verified": False,
    }
    report["readback_sha256"] = _hash(report)
    return report


def verify(report: dict, workspace: Path, job_id: str,
           evidence_folder: Path) -> None:
    """No self-hashed acceptance: rebuild from every current raw file."""
    if not isinstance(report, dict) or report != build(
        workspace, job_id, evidence_folder,
    ):
        raise Element7ReadbackError(
            "Element 7 native readback is stale, incomplete or modified."
        )
