"""Element 8 bounded CineTwin repair triage and independent remeasurement.

A repair *suggestion* never grants native edit rights. Reuses the exact Element 7
source/target comparison, Element 3 per-occurrence attribution, and existing
CineTwin recovery budget; the only executable adapters remain independently
user-authorized through the existing Studio agent graph and Unreal executor.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import studio_element7_readback as element7
import studio_element_cinetwin as cinetwin

KIND = "cutsceneai.studio.element8_bounded_repair"
VERSION = "1"
MAX_OBSERVATIONS = cinetwin.MAX_REMEASURE_ATTEMPTS + 1
SHA = re.compile(r"[a-f0-9]{64}\Z")
OPTIONS = frozenset({
    "REPORT_LIMITATION",
    "INVESTIGATE_TARGET_MAPPING",
    "INSPECT_EXISTING_USER_AUTHORIZED_CHARACTER_OFFSET_POLICY",
    "INSPECT_SKELETAL_RETARGETING_AND_CALIBRATION",
    "INSPECT_APPROVED_MESH_ANATOMICAL_FORWARD_BASIS",
    "INSPECT_NATIVE_CAMERA_LENS",
    "INSPECT_NATIVE_CAMERA_CUT_BINDINGS",
    "INSPECT_OTHER_NATIVE_DOMAIN",
})


class BoundedRepairError(ValueError):
    """Malformed, changed or insufficient native evidence; no repair authorized."""


def _hash(document: Any) -> str:
    return hashlib.sha256(json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _snapshot(candidate: Path) -> dict | None:
    pointer = candidate / "element-workflow-active.json"
    if not pointer.exists():
        return None
    data, _ = element7._safe_json(pointer)
    digest = data.get("workflow_sha256")
    if not isinstance(digest, str) or not SHA.fullmatch(digest):
        raise BoundedRepairError("Active source occurrence workflow is invalid.")
    report, _ = element7._safe_json(candidate / (
        "element-workflow-" + digest + ".json"
    ))
    if (report.get("workflow_sha256") != digest
            or report.get("candidate_id") != data.get("candidate_id")
            or digest != _hash({
                key: value for key, value in report.items()
                if key != "workflow_sha256"
            })):
        raise BoundedRepairError("Source occurrence workflow changed.")
    return report


def _recommend(item: dict) -> str:
    """No guesses about causation. Safely named installed policy, not a grant."""
    flags = set(item["discrepancy_flags"])
    if item["measurement_status"] == "INCOMPLETE_TARGET_UNMAPPED":
        return "INVESTIGATE_TARGET_MAPPING"
    if item["measurement_status"] != "DIRECT_MEASURED_DIFFERENCE":
        return "REPORT_LIMITATION"
    if (
        item["recovery_hint"]
        == "INSPECT_EXISTING_USER_AUTHORIZED_CHARACTER_OFFSET_POLICY"
        and item["ced"] == "entity.character"
        and flags == {"WORLD_POSITION_OUTSIDE_TOLERANCE"}
        and item["measured"].get("actor_rotation_degrees", 181) <= 0.5
        and item["measured"].get("skeletal_joint_status") != "FAIL"
    ):
        # This is only a review of the existing exact-character correction
        # adapter; that adapter independently measures root/actor motion,
        # checks explicit user feedback and rolls back unsuccessful changes.
        return "INSPECT_EXISTING_USER_AUTHORIZED_CHARACTER_OFFSET_POLICY"
    if flags == {"CHARACTER_MESH_ANATOMICAL_FORWARD_MISMATCH"}:
        # The native CineTwin comparison may contain an independently
        # approved mesh-forward profile, but its yaw candidate remains a
        # diagnostic: it does not prove actor/Sequencer transform ownership,
        # a stable imported FBX basis, safe rollback or permission to edit.
        return "INSPECT_APPROVED_MESH_ANATOMICAL_FORWARD_BASIS"
    if any(
        flag.startswith("SKELETAL_") or flag.startswith("SOURCE_BONES_")
        or flag.startswith("CALIBRATED_") or flag.startswith("CHARACTER_MESH_")
        for flag in flags
    ):
        return "INSPECT_SKELETAL_RETARGETING_AND_CALIBRATION"
    if "CAMERA_NATIVE_LENS_DIFFERENCE" in flags:
        return "INSPECT_NATIVE_CAMERA_LENS"
    if "GLOBAL_CAMERA_CUT_TIMING_DIFFERENCE" in flags:
        return "INSPECT_NATIVE_CAMERA_CUT_BINDINGS"
    return "INSPECT_OTHER_NATIVE_DOMAIN"


def build(workspace: Path, job_id: str,
          evidence_folders: list[Path]) -> dict[str, Any]:
    """Pure evidence triage: 1 baseline and at most two independent rechecks."""
    if (not isinstance(evidence_folders, list)
            or not 1 <= len(evidence_folders) <= MAX_OBSERVATIONS):
        raise BoundedRepairError(
            "Element 8 requires one source-bound baseline and at most two remeasurements."
        )
    root = Path(workspace).resolve()
    proofs = []
    target_observations = []
    observations = []
    candidate = None
    raw_source = None
    source_capture = None
    sampling = None
    for index, supplied in enumerate(evidence_folders):
        try:
            base, location, folder, job = element7._bound_paths(
                root, job_id, Path(supplied),
            )
            proof = element7.build(base, job_id, folder)
            persisted = folder / "element7-readback.json"
            if persisted.exists():
                document, _ = element7._safe_json(persisted)
                if document != proof:
                    raise BoundedRepairError(
                        "Persisted Element 7 readback differs from the raw evidence."
                    )
            capture, capture_sha = element7._safe_json(
                folder / "target-behavior.json"
            )
        except (element7.Element7ReadbackError, OSError, ValueError,
                KeyError, TypeError) as exc:
            raise BoundedRepairError(
                "Element 8 cannot trust native baseline/remeasurement evidence."
            ) from exc
        if candidate is None:
            candidate = location
            raw_source, _ = element7._safe_json(Path(job["csir"]))
            source_capture, _ = element7._safe_json(Path(job["capture"]))
            sampling, _ = element7._safe_json(
                folder / "sampling-plan.json"
            )
        elif candidate != location:
            raise BoundedRepairError("Remeasurement belongs to a foreign candidate.")
        if proof["native_attempt"]["status"] != (
            "SOURCE_BOUND_NATIVE_BUILDER_COMPLETED"
        ):
            # Can't propose repairs based on unknown, interrupted or partially
            # executed native transfer whose actual target may be corrupted.
            raise BoundedRepairError(
                "Existing native transfer is not a verified completed builder attempt."
            )
        if index and any(
            proof[key] != proofs[0][key]
            for key in (
                "job_id_sha256", "candidate_id_sha256",
                "sequence_identity_sha256", "source_csir_file_sha256",
                "source_capture_file_sha256", "prepared_plan_file_sha256",
                "prepared_session_file_sha256", "target_mapping_file_sha256",
            )
        ):
            raise BoundedRepairError("Native remeasurement source or plan changed.")
        if index and capture_sha in observations:
            raise BoundedRepairError(
                "Duplicate native capture cannot be an independent remeasurement."
            )
        observations.append(capture_sha)
        proofs.append(proof)
        target_observations.append(capture)
    assert candidate is not None and raw_source is not None
    assert sampling is not None and source_capture is not None
    workflow = _snapshot(candidate)
    if workflow is not None and any(
        not isinstance(proof.get("element_occurrence_attribution"), dict)
        or proof["element_occurrence_attribution"].get("workflow_sha256")
        != workflow["workflow_sha256"]
        for proof in proofs
    ):
        raise BoundedRepairError(
            "Target samples do not match the latest exact source occurrence workflow."
        )
    outcomes = []
    recheck = None
    if workflow is not None:
        # Element 7 has already checked the exact Element 3/4/5 approval and
        # fully re-attributed every source occurrence for each observation.
        baseline = cinetwin.build(
            raw_source, workflow["element_plan"], sampling,
            source_capture, target_observations[0],
        )
        if len(target_observations) > 1:
            try:
                recheck = cinetwin.remeasure(
                    raw_source, workflow["element_plan"], sampling,
                    source_capture, target_observations,
                )
            except (cinetwin.ElementCineTwinError, ValueError,
                    KeyError, TypeError) as exc:
                raise BoundedRepairError(
                    "Independent CineTwin remeasurement has failed or regressed."
                ) from exc
        latest = cinetwin.build(
            raw_source, workflow["element_plan"], sampling,
            source_capture, target_observations[-1],
        )
        review = {
            row["occurrence_id"]: row
            for row in recheck["per_occurrence"]
        } if recheck is not None else {}
        for before, after in zip(
            baseline["occurrences"], latest["occurrences"],
        ):
            if before["occurrence_id"] != after["occurrence_id"]:
                raise BoundedRepairError("Source occurrence order changed.")
            progress = review.get(before["occurrence_id"], {})
            action = _recommend(after)
            if progress.get("result") in {
                "STOP_REPEATED_NO_MEASURED_IMPROVEMENT",
                "REGRESSED_AFTER_REMEASUREMENT",
            }:
                action = "REPORT_LIMITATION"
            # One previously resolved source element needs no further edits.
            if after["measurement_status"] != "DIRECT_MEASURED_DIFFERENCE":
                if after["measurement_status"] != "INCOMPLETE_TARGET_UNMAPPED":
                    action = "REPORT_LIMITATION"
            outcomes.append({
                "occurrence_id": after["occurrence_id"],
                "source_kind": after["source_kind"],
                "baseline_status": before["measurement_status"],
                "latest_status": after["measurement_status"],
                "latest_discrepancy_flags": after["discrepancy_flags"],
                "measured_actor_position_error_cm": after["measured"].get(
                    "actor_position_cm"
                ),
                "remeasurement_result": progress.get(
                    "result", "BASELINE_ONLY"
                ),
                "advisory_strategy": action,
                "model_override_allowed": False,
                "native_edit_authorized": False,
                "automatic_native_retry_authorized": False,
                "full_cutscene_fidelity_verified": False,
            })
    # Native lens and cut findings are GLOBAL measurements. They must not
    # be assigned causal blame to an individual Timeline track/section.
    latest_proof = proofs[-1]
    domain_findings = [{
        "domain": domain, "status": latest_proof[field],
        "advisory_strategy": (
            strategy if latest_proof[field] in ("FAIL", "INCOMPLETE")
            else "REPORT_LIMITATION"
        ),
        "source_track_causality_verified": False,
        "native_edit_authorized": False,
    } for domain, field, strategy in (
        ("camera_lens", "camera_lens_status",
         "INSPECT_NATIVE_CAMERA_LENS"),
        ("camera_cuts", "camera_cuts_status",
         "INSPECT_NATIVE_CAMERA_CUT_BINDINGS"),
    )]
    any_difference = any(
        entry["measured_scope_status"]
        == "MEASURED_NATIVE_DIFFERENCES_DETECTED"
        for entry in proofs
    )
    regressed = any(
        row["remeasurement_result"] in {
            "STOP_REPEATED_NO_MEASURED_IMPROVEMENT",
            "REGRESSED_AFTER_REMEASUREMENT",
        } for row in outcomes
    )
    attempts = len(proofs) - 1
    if regressed:
        status = "STOP_MEASURED_REGRESSION_OR_NO_PROGRESS"
    elif attempts >= cinetwin.MAX_REMEASURE_ATTEMPTS:
        status = "STOP_REMEASUREMENT_BUDGET_EXHAUSTED"
    elif proofs[-1]["measured_scope_status"] == (
        "MEASURED_NATIVE_SCOPE_WITHIN_TOLERANCE"
    ) and not any(
        row["latest_status"] == "DIRECT_MEASURED_DIFFERENCE"
        for row in outcomes
    ):
        status = "MEASURED_DOMAINS_CLEAR_OTHER_FIDELITY_UNVERIFIED"
    elif not outcomes:
        status = "REPORT_ONLY_NO_EXACT_SOURCE_OCCURRENCE_PLAN"
    elif any_difference:
        status = "INVESTIGATE_APPROVED_NARROW_ADAPTER_OR_REPORT_LIMITATION"
    else:
        status = "SOURCE_GAPS_OR_UNMEASURED_DOMAINS_REMAIN"
    # The _remeasure plan may recommend another *human-measured capture*.
    # This never enables automatic Unreal re-execution or a native edit.
    manual_check_possible = (
        not regressed and attempts < cinetwin.MAX_REMEASURE_ATTEMPTS
        and bool(outcomes)
        and bool(any(
            row["latest_status"] == "DIRECT_MEASURED_DIFFERENCE"
            for row in outcomes
        ))
        and (recheck is None or recheck["next_attempt_recommended"])
    )
    public = {
        "kind": KIND, "schema_version": VERSION,
        "job_id_sha256": proofs[0]["job_id_sha256"],
        "candidate_id_sha256": proofs[0]["candidate_id_sha256"],
        "native_sequence_sha256": proofs[0]["sequence_identity_sha256"],
        "source_csir_file_sha256": proofs[0]["source_csir_file_sha256"],
        "source_capture_file_sha256": proofs[0]["source_capture_file_sha256"],
        "native_execution_claim_sha256":
            proofs[0]["native_attempt"]["claim_sha256"],
        "element7_readback_sha256s": [
            entry["readback_sha256"] for entry in proofs
        ],
        "native_capture_file_sha256s": observations,
        "element3_workflow_sha256": (
            workflow["workflow_sha256"] if workflow else None
        ),
        "source_occurrence_count": len(outcomes) if workflow else None,
        "native_measurement_count": len(proofs),
        "remeasurement_attempts": attempts,
        "remaining_manual_observation_budget":
            cinetwin.MAX_REMEASURE_ATTEMPTS - attempts,
        "status": status,
        "manual_remeasurement_possible": manual_check_possible,
        "native_repair_adapter_available_for_review": any(
            row["advisory_strategy"]
            == "INSPECT_EXISTING_USER_AUTHORIZED_CHARACTER_OFFSET_POLICY"
            for row in outcomes
        ),
        "per_occurrence": outcomes,
        "domain_findings": domain_findings,
        "unverified_domains": sorted(set(
            domain for proof in proofs
            for domain in proof["unverified_domains"]
        )),
        "strategy_policy":
            "DETERMINISTIC_READ_ONLY_EXACT_SOURCE_NO_ARBITRARY_REPAIR",
        "existing_native_character_offset_requires_explicit_user_feedback": True,
        "native_repair_authorized": False,
        "automatic_native_retry_authorized": False,
        "full_cutscene_fidelity_verified": False,
        "independent_engine_attestation_verified": False,
    }
    if any(
        finding["status"] == "FAIL" for finding in domain_findings
    ) and status == "SOURCE_GAPS_OR_UNMEASURED_DOMAINS_REMAIN":
        public["status"] = "NATIVE_CAMERA_DOMAIN_REQUIRES_MANUAL_INVESTIGATION"
    public["repair_plan_sha256"] = _hash(public)
    return public


def verify(report: dict, workspace: Path, job_id: str,
           evidence_folders: list[Path]) -> None:
    if (not isinstance(report, dict)
            or report != build(workspace, job_id, evidence_folders)):
        raise BoundedRepairError(
            "Saved Element 8 repair triage changed or became stale."
        )


def save_once(workspace: Path, job_id: str,
              evidence_folders: list[Path]) -> tuple[Path, dict]:
    """Create an immutable review record. Never alter editor or queued job."""
    report = build(workspace, job_id, evidence_folders)
    root, candidate, _, _ = element7._bound_paths(
        workspace, job_id, evidence_folders[0],
    )
    assert root == Path(workspace).resolve()
    path = candidate / ("element8-repair-plan-" + report[
        "repair_plan_sha256"
    ] + ".json")
    if path.exists():
        stored, _ = element7._safe_json(path)
        verify(stored, workspace, job_id, evidence_folders)
    else:
        with path.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, sort_keys=True,
                      allow_nan=False)
            stream.write("\n")
            stream.flush()
    return path, report


def select_advisory(report: dict, occurrence_id: str,
                    strategy: str) -> dict:
    """Bound a model suggestion to a single deterministically allowed option.

    A returned selection remains advisory, and cannot create a native request.
    """
    if (not isinstance(report, dict) or report.get("kind") != KIND
            or report.get("repair_plan_sha256") != _hash({
                key: value for key, value in report.items()
                if key != "repair_plan_sha256"
            })
            or not isinstance(strategy, str) or strategy not in OPTIONS):
        raise BoundedRepairError("An untrusted model repair strategy was rejected.")
    row = next((entry for entry in report.get("per_occurrence", [])
                if entry.get("occurrence_id") == occurrence_id), None)
    if (not row or row.get("advisory_strategy") != strategy
            or row.get("native_edit_authorized") is not False
            or report.get("native_repair_authorized") is not False
            or report.get("automatic_native_retry_authorized") is not False):
        raise BoundedRepairError(
            "A model cannot expand native repair scope or override measured evidence."
        )
    return {
        "kind": "cutsceneai.studio.element8_advisory_selection",
        "occurrence_id": occurrence_id, "strategy": strategy,
        "repair_plan_sha256": report["repair_plan_sha256"],
        "native_execution_requested": False,
        "native_repair_authorized": False,
        "full_cutscene_fidelity_verified": False,
    }



def may_review_exact_character_offset(
    workspace: Path, job_id: str, evidence_folders: list[Path],
    target_entity_name: str,
) -> bool:
    """Check one locally named character without exposing names in reports.

    A report-level 'some character offset exists' is NOT permission to apply
    an edit to a different character selected by a model or stale UI.
    """
    if (not isinstance(target_entity_name, str)
            or not target_entity_name or len(target_entity_name) > 256):
        return False
    report = build(workspace, job_id, evidence_folders)
    if (report["status"] in {
            "STOP_MEASURED_REGRESSION_OR_NO_PROGRESS",
            "STOP_REMEASUREMENT_BUDGET_EXHAUSTED",
        } or not report["native_repair_adapter_available_for_review"]):
        return False
    root, candidate, _, job = element7._bound_paths(
        workspace, job_id, evidence_folders[0],
    )
    assert root == Path(workspace).resolve()
    workflow = _snapshot(candidate)
    if workflow is None:
        return False
    csir, _ = element7._safe_json(Path(job["csir"]))
    candidates = []
    for occurrence in workflow["element_plan"]["elements"]:
        if occurrence.get("source_kind") != "entities":
            continue
        match = re.fullmatch(
            r"entities\[(\d+)\]", str(occurrence.get("source_location") or "")
        )
        if match is None:
            raise BoundedRepairError(
                "Element 8 original source entity location has changed."
            )
        index = int(match.group(1))
        if not 0 <= index < len(csir.get("entities", [])):
            raise BoundedRepairError("Element 8 source occurrence index is invalid.")
        native_source = csir["entities"][index]
        if (native_source.get("name") == target_entity_name
                and native_source.get("ced_type") == "entity.character"):
            candidates.append(occurrence["occurrence_id"])
    if len(candidates) != 1:
        return False
    record = [
        row for row in report["per_occurrence"]
        if row["occurrence_id"] == candidates[0]
    ]
    return len(record) == 1 and record[0]["advisory_strategy"] == (
        "INSPECT_EXISTING_USER_AUTHORIZED_CHARACTER_OFFSET_POLICY"
    )
