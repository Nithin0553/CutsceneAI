"""Element 9 — source-complete, non-executable remeasurement/limitation outcome.

Build from exact prepared Unity evidence and (when available) independently
reconstructed Element 7 readback + Element 8 bounded recovery evidence.
An incomplete source, a missing observation or an exhausted repair budget
is a documented limitation, never a claimed successful native conversion.

All output is anonymized, read-only, deterministic, candidate/job-bound, and
independently reconstructable. No automatic retry, engine write or new repair.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

import feature_dispatch
import studio_element5_plan
import studio_element7_readback as readback
import studio_element8_repair as repair

KIND = "cutsceneai.studio.element9_final_outcome"
VERSION = "1"
MAX_SOURCE_OCCURRENCES = 30000
PAGE_SIZE = 50
HEX = re.compile(r"[a-f0-9]{64}\Z")
JOB_ID = re.compile(r"[a-f0-9]{32}\Z")
CANDIDATE = re.compile(r"[0-9]{8}T[0-9]{6}Z_[a-f0-9]{8}\Z")
UNMEASURED_REQUIRED_DOMAINS = (
    "rendered_frame_parity",
    "full_skeletal_pose",
    "audio_and_event_behavior",
    "physics_and_simulation",
    "materials_and_lighting",
    "custom_gameplay_and_scripts",
    "heldout_project_validation",
)
STOP_STATES = frozenset({
    "STOP_MEASURED_REGRESSION_OR_NO_PROGRESS",
    "STOP_REMEASUREMENT_BUDGET_EXHAUSTED",
})


class OutcomeError(ValueError):
    """Final outcome cannot be established from changed or foreign evidence."""


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def _file(path: Path) -> tuple[dict, str]:
    return readback._safe_json(path)


def _context(workspace: Path, job_id: str) -> tuple[Path, Path, dict, dict, dict, dict]:
    """Verify immutable candidate/source identity even BEFORE engine capture."""
    root = Path(workspace).resolve()
    if not isinstance(job_id, str) or not JOB_ID.fullmatch(job_id):
        raise OutcomeError("Native job identity is invalid.")
    if (root / "jobs").is_symlink() or (root / "candidates").is_symlink():
        raise OutcomeError("Native job or candidate directory is unsafe.")
    job, _ = _file(root / "jobs" / (job_id + ".json"))
    identifier = job.get("candidate_id")
    if (job.get("kind") != "cutsceneai.studio.local_unreal_job"
            or job.get("job_id") != job_id
            or not isinstance(identifier, str) or not CANDIDATE.fullmatch(identifier)):
        raise OutcomeError("Native job/candidate identity is invalid.")
    candidate = root / "candidates" / identifier
    if (candidate.is_symlink() or not candidate.is_dir()
            or candidate.resolve().parent != (root / "candidates").resolve()
            or candidate.resolve() != Path(
                str(job.get("candidate_dir") or "")
            ).resolve()):
        raise OutcomeError("Native evidence is not in its prepared candidate.")
    session, _ = _file(candidate / "session.json")
    source, source_sha = _file(Path(str(job.get("csir") or "")))
    mapping, mapping_sha = _file(Path(str(job.get("mapping") or "")))
    compiled, compiled_sha = _file(candidate / "transfer-plan.json")
    if (session.get("kind") != "cutsceneai.studio.prepared_transfer"
            or session.get("source", {}).get("csir_path") != job.get("csir")
            or session.get("source", {}).get("sha256") != source_sha
            or session.get("target", {}).get("mapping_path") != job.get("mapping")
            or session.get("target", {}).get("sequence_asset_path")
            != job.get("sequence_path")
            or session.get("artifact_sha256", {}).get("transfer-plan.json")
            != compiled_sha
            or mapping.get("sequence_asset_path") != job.get("sequence_path")
            or compiled.get("sequence_asset_path") != job.get("sequence_path")):
        raise OutcomeError("Original prepared source, mapping or action plan changed.")
    capture_path = Path(str(job.get("capture") or ""))
    if session.get("source_capture"):
        _, capture_sha = _file(capture_path)
        if (session["source_capture"].get("path") != job.get("capture")
                or session["source_capture"].get("sha256") != capture_sha):
            raise OutcomeError("Original Unity source observation is stale.")
    return root, candidate, job, source, mapping, compiled


def discover(workspace: Path, job_id: str) -> list[Path]:
    """Fail closed on partial, excess, or symlinked native observation folders."""
    _, candidate, _, _, _, _ = _context(workspace, job_id)
    entries = []
    for path in candidate.glob("native-acceptance-*"):
        if path.is_symlink() or not path.is_dir():
            raise OutcomeError("Native acceptance folder is not a safe directory.")
        # A partially written observer output cannot be silently skipped,
        # turning corrupted evidence into a misleading 'not tested' result.
        if not (path / "element7-readback.json").exists():
            raise OutcomeError(
                "Native acceptance exists but independently verified Element 7 "
                "evidence is missing; report the incomplete observation."
            )
        if (path / "element7-readback.json").is_symlink():
            raise OutcomeError("Native readback link is unsafe.")
        entries.append(path)
    if len(entries) > repair.MAX_OBSERVATIONS:
        raise OutcomeError("Element 8's bounded native observation budget was exceeded.")
    # Filesystem mtime is a display ordering, not engine-attested causal order.
    return sorted(entries, key=lambda path: (
        path.stat().st_mtime_ns, path.name,
    ))


def _source_rows(candidate: Path, job: dict, source: dict,
                 mapping: dict, compiled: dict) -> tuple[list[dict], str | None]:
    """Full Element 3/5 structural source coverage; no proprietary names."""
    workflow = repair._snapshot(candidate)
    if workflow is None:
        try:
            entries = feature_dispatch._source_rows(source)
        except (feature_dispatch.FeatureDispatchError, ValueError,
                KeyError, TypeError) as exc:
            raise OutcomeError("Source occurrence inventory could not be enumerated.") from exc
        if len(entries) > MAX_SOURCE_OCCURRENCES:
            raise OutcomeError("Source inventory exceeds bounded report size.")
        return [{
            "occurrence_id": f"E{index:05d}", "source_kind": entry["kind"],
            "conversion_plan_state": "NO_ELEMENT5_SOURCE_BOUND_PLAN",
            "explicitly_attributed_action_ids": [],
        } for index, entry in enumerate(entries)], None
    try:
        if (workflow.get("source_file_sha256") != _file(Path(job["csir"]))[1]
                or workflow.get("candidate_mapping_sha256")
                != _file(Path(job["mapping"]))[1]
                or workflow.get("transfer_plan_sha256")
                != _file(candidate / "transfer-plan.json")[1]):
            raise OutcomeError("Element 3/5 source workflow differs from prepared evidence.")
        studio_element5_plan.verify(
            workflow["element5_source_bound_plan"],
            source, mapping, compiled,
            workflow["element_plan"], workflow["element_schedule"],
            workflow["element_strategy"],
            workflow["element4_baseline_validation"],
        )
        entries = workflow["element5_source_bound_plan"]["source_occurrences"]
        if (len(entries) > MAX_SOURCE_OCCURRENCES
                or len(entries) != workflow["element_plan"]["source_occurrence_count"]):
            raise OutcomeError("Element 5 omitted source occurrences.")
        return [{
            "occurrence_id": row["occurrence_id"],
            "source_kind": row["source_kind"],
            "conversion_plan_state": row["conversion_plan_state"],
            "explicitly_attributed_action_ids":
                list(row["explicitly_attributed_action_ids"]),
        } for row in entries], workflow["workflow_sha256"]
    except (studio_element5_plan.SourceBoundPlanError, KeyError,
            TypeError, ValueError) as exc:
        raise OutcomeError("Element 3/4/5 source-bound ledger is modified or stale.") from exc


def _classify(before: dict, measured: dict | None) -> tuple[str, str]:
    if measured is None:
        if before["conversion_plan_state"] == (
            "UNKNOWN_SEMANTIC_RETAINED_FOR_INVESTIGATION"
        ):
            return "UNKNOWN_SEMANTIC_NOT_MEASURED", "DOCUMENT_UNSUPPORTED_SOURCE_CONCEPT"
        if before["conversion_plan_state"] == "TARGET_REFERENCE_NOT_MAPPED":
            return "TARGET_MAPPING_NOT_VERIFIED", "REVIEW_EXACT_SOURCE_TARGET_MAPPING"
        return "NATIVE_OBSERVATION_PENDING", "CAPTURE_REAL_REOPENED_EDITOR_EVIDENCE"
    status = measured["latest_status"]
    if status == "DIRECT_MEASURED_DIFFERENCE":
        return "MEASURED_DIFFERENCE_REMAINS", "REPORT_OR_REVIEW_NARROW_SUPPORTED_CORRECTION"
    if status == "DIRECT_MEASURED_NO_FLAGGED_DIFFERENCE":
        if measured["baseline_status"] == "DIRECT_MEASURED_DIFFERENCE":
            return "MEASURED_IMPROVEMENT_NO_CAUSAL_PROOF", "NO_FURTHER_AUTOMATIC_REPAIR"
        return "MEASURED_SCOPE_NO_FLAGGED_DIFFERENCE", "NO_FURTHER_AUTOMATIC_REPAIR"
    if status == "INCOMPLETE_TARGET_UNMAPPED":
        return "TARGET_MAPPING_NOT_VERIFIED", "REVIEW_EXACT_SOURCE_TARGET_MAPPING"
    if status == "DIRECT_MEASUREMENT_INCOMPLETE":
        return "MEASURED_SCOPE_INCOMPLETE", "REPORT_UNMEASURED_DOMAIN"
    return "SOURCE_OCCURRENCE_UNMEASURED_OR_UNATTRIBUTED", "REPORT_UNMEASURED_DOMAIN"


def build(workspace: Path, job_id: str,
          evidence_folders: list[Path] | None = None) -> dict[str, Any]:
    """Recompute all bounded evidence, even for a job with zero observations."""
    root, candidate, job, source, mapping, compiled = _context(workspace, job_id)
    rows, workflow_digest = _source_rows(candidate, job, source, mapping, compiled)
    folders = (discover(root, job_id) if evidence_folders is None
               else list(evidence_folders))
    if (len(folders) > repair.MAX_OBSERVATIONS
            or len({str(Path(p).resolve()) for p in folders}) != len(folders)):
        raise OutcomeError("Duplicate or excessive CineTwin observations are prohibited.")
    triage = None
    proofs = []
    if folders:
        try:
            triage = repair.build(root, job_id, folders)
            for folder in folders:
                proof = readback.build(root, job_id, Path(folder))
                stored, _ = _file(Path(folder) / "element7-readback.json")
                if stored != proof:
                    raise OutcomeError(
                        "Saved native readback was modified after measurement."
                    )
                proofs.append(proof)
        except (repair.BoundedRepairError, readback.Element7ReadbackError,
                ValueError, TypeError, KeyError, OSError) as exc:
            raise OutcomeError(
                "Native remeasurement or bounded repair evidence is invalid."
            ) from exc
        if triage["element3_workflow_sha256"] != workflow_digest:
            raise OutcomeError("Readback belongs to a different source occurrence workflow.")
        if triage["source_occurrence_count"] not in (None, len(rows)):
            raise OutcomeError("Remeasurement omits original source occurrences.")
        if (workflow_digest is not None
                and triage["source_occurrence_count"] != len(rows)):
            raise OutcomeError("Exact-source remeasurement is incomplete.")
        if not all(
            proof["source_csir_file_sha256"] == _file(Path(job["csir"]))[1]
            for proof in proofs
        ):
            raise OutcomeError("Reopened native samples differ from prepared Unity source.")
    findings = {
        entry["occurrence_id"]: entry for entry in triage["per_occurrence"]
    } if triage is not None else {}
    if findings and set(findings) != {
        entry["occurrence_id"] for entry in rows
    }:
        raise OutcomeError("Element 8 lost or duplicated a source occurrence.")
    occurrences = []
    for source_row in rows:
        ident = source_row["occurrence_id"]
        measured = findings.get(ident)
        if measured is not None and measured["source_kind"] != source_row["source_kind"]:
            raise OutcomeError("Element 8 source occurrence kind changed.")
        status, next_step = _classify(source_row, measured)
        if triage is not None and triage["status"] in STOP_STATES:
            if status == "MEASURED_DIFFERENCE_REMAINS":
                next_step = "STOP_BOUNDED_REPAIR_REPORT_LIMITATION"
        occurrences.append({
            "occurrence_id": ident,
            "source_kind": source_row["source_kind"],
            "source_plan_status": source_row["conversion_plan_state"],
            "explicit_native_source_action_count": len(
                source_row["explicitly_attributed_action_ids"]
            ),
            "outcome": status,
            "next_step": next_step,
            "baseline_measurement_status":
                measured["baseline_status"] if measured else None,
            "latest_measurement_status":
                measured["latest_status"] if measured else None,
            "measurement_progress":
                measured["remeasurement_result"] if measured else None,
            "remaining_discrepancy_flags":
                list(measured["latest_discrepancy_flags"]) if measured else [],
            "native_equivalence_proven": False,
            "full_cinematic_fidelity_proven": False,
        })
    summary = Counter(row["outcome"] for row in occurrences)
    latest = proofs[-1] if proofs else None
    domains = [{
        "domain": field,
        "outcome": "MEASURED_SCOPE_ONLY_NOT_ENGINE_ATTESTED"
        if latest and latest["measured_scope_status"] == (
            "MEASURED_NATIVE_SCOPE_WITHIN_TOLERANCE"
        ) else "MEASURED_DIFFERENCE_OR_INCOMPLETE"
        if latest else "NATIVE_OBSERVATION_PENDING",
        "full_fidelity_verified": False,
    } for field in ("actor_transform", "skeletal_motion",
                    "camera_lens", "camera_cuts")]
    domains.extend({
        "domain": field,
        "outcome": "UNVERIFIED_REQUIRES_SEPARATE_ACCEPTANCE",
        "full_fidelity_verified": False,
    } for field in UNMEASURED_REQUIRED_DOMAINS)
    if latest is not None:
        for field in latest["unverified_domains"]:
            if (not isinstance(field, str)
                    or not re.fullmatch(r"[a-z][a-z0-9_]{0,79}", field)):
                raise OutcomeError("CineTwin unverified-domain identifier is unsafe.")
        known = {x["domain"] for x in domains}
        domains.extend({
            "domain": field,
            "outcome": "UNVERIFIED_REQUIRES_SEPARATE_ACCEPTANCE",
            "full_fidelity_verified": False,
        } for field in sorted(set(latest["unverified_domains"]) - known))
    if not triage:
        status = "NATIVE_ACCEPTANCE_PENDING_ALL_SOURCE_OCCURRENCES_UNVERIFIED"
        followup = "CAPTURE_ACTUAL_SAVED_AND_REOPENED_UNREAL_SEQUENCE"
    elif triage["status"] == "STOP_MEASURED_REGRESSION_OR_NO_PROGRESS":
        status = "STOP_REPAIR_NO_MEASURED_IMPROVEMENT_REPORT_LIMITATIONS"
        followup = "MANUAL_INVESTIGATION_NEW_EXPLICIT_APPROVAL_REQUIRED"
    elif triage["status"] == "STOP_REMEASUREMENT_BUDGET_EXHAUSTED":
        status = "STOP_REMEASUREMENT_BUDGET_REPORT_LIMITATIONS"
        followup = "MANUAL_INVESTIGATION_NEW_EXPLICIT_APPROVAL_REQUIRED"
    elif latest["measured_scope_status"] == "MEASURED_NATIVE_DIFFERENCES_DETECTED":
        status = "MEASURED_DIFFERENCES_REMAIN_LIMITATIONS_RECORDED"
        followup = "REVIEW_SUPPORTED_REPAIR_OR_REPORT_LIMITATION"
    elif latest["measured_scope_status"] == "MEASURED_NATIVE_SCOPE_WITHIN_TOLERANCE":
        status = "MEASURED_SCOPE_WITHIN_TOLERANCE_FULL_FIDELITY_UNVERIFIED"
        followup = "INDEPENDENT_FULL_CINEMATIC_ACCEPTANCE_REQUIRED"
    else:
        status = "NATIVE_MEASUREMENT_GAPS_REMAIN_LIMITATIONS_RECORDED"
        followup = "REPORT_UNMEASURED_DOMAINS_OR_REMEASURE_WITHIN_BUDGET"
    result = {
        "kind": KIND,
        "schema_version": VERSION,
        "job_id_sha256": _hash(job_id),
        "candidate_id_sha256": _hash(job["candidate_id"]),
        "source_csir_sha256": readback._safe_json(Path(job["csir"]))[1],
        "source_workflow_sha256": workflow_digest,
        "element8_repair_plan_sha256": (
            triage["repair_plan_sha256"] if triage else None
        ),
        "native_readback_sha256s": [
            proof["readback_sha256"] for proof in proofs
        ],
        "observation_order_basis":
            "CALLER_ORDER_OR_FILESYSTEM_MTIME_NOT_ENGINE_ATTESTED",
        "native_observation_count": len(proofs),
        "bounded_remeasurement_attempt_count": max(0, len(proofs) - 1),
        "remaining_manual_remeasurement_budget": (
            triage["remaining_manual_observation_budget"]
            if triage else repair.MAX_OBSERVATIONS - 1
        ),
        "measured_improvement_is_not_repair_causality": True,
        "source_occurrence_count": len(rows),
        "source_outcome_counts": dict(sorted(summary.items())),
        "source_occurrences": occurrences,
        "measured_and_unverified_domains": domains,
        "status": status,
        "next_step": followup,
        "stop_reason": (
            triage["status"] if triage and triage["status"] in STOP_STATES
            else None
        ),
        "native_builder_receipt_consistent_with_saved_evidence": bool(
            latest and latest["native_attempt"]["native_builder_completed"]
        ),
        "independent_engine_attestation_verified": False,
        "manual_review_required": True,
        "native_repair_authorized": False,
        "automatic_native_retry_authorized": False,
        "full_cutscene_fidelity_verified": False,
        "release_ready": False,
    }
    result["outcome_sha256"] = _hash(result)
    return result


def verify(report: dict, workspace: Path, job_id: str,
           evidence_folders: list[Path] | None = None) -> None:
    if not isinstance(report, dict) or report != build(
        workspace, job_id, evidence_folders,
    ):
        raise OutcomeError("Element 9 saved outcome is stale or altered.")


def save_once(workspace: Path, job_id: str,
              evidence_folders: list[Path] | None = None) -> tuple[Path, dict]:
    """Immutable candidate-local document; no engine/model/job mutations."""
    report = build(workspace, job_id, evidence_folders)
    _, candidate, _, _, _, _ = _context(workspace, job_id)
    output = candidate / ("element9-outcome-" + report["outcome_sha256"] + ".json")
    if output.exists():
        saved, _ = _file(output)
        verify(saved, workspace, job_id, evidence_folders)
    else:
        try:
            with output.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(report, stream, sort_keys=True,
                          ensure_ascii=False, allow_nan=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError as exc:
            raise OutcomeError("Concurrent Element 9 outcome write cannot overwrite.") from exc
    return output, report


def page(report: dict, offset: int = 0) -> dict[str, Any]:
    """Bounded redacted UI view: pagination never changes report identity."""
    if (not isinstance(report, dict) or report.get("kind") != KIND
            or report.get("outcome_sha256") != _hash({
                key: value for key, value in report.items()
                if key != "outcome_sha256"
            })
            or type(offset) is not int or offset < 0
            or offset > MAX_SOURCE_OCCURRENCES):
        raise OutcomeError("Final outcome or page offset is invalid.")
    view = {
        key: value for key, value in report.items()
        if key != "source_occurrences"
    }
    view.update({
        "available": True,
        "page_offset": offset,
        "page_size": PAGE_SIZE,
        "source_page": report["source_occurrences"][offset:offset + PAGE_SIZE],
    })
    return view
