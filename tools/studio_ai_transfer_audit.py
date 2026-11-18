"""Read-only, job-bound audit of AI planning versus native Unreal execution.

Do not infer real-engine execution from an LLM reply, UI toast, or a prepared
plan. For a generated candidate, bind the model decision, immutable plan,
Unreal's own builder receipt and source-authenticated CineTwin measurements.
No engine mutation and no secret/raw scene data in the web response.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

JOB_ID = re.compile(r"[0-9a-f]{32}\Z")
KIND = "cutsceneai.studio.ai_transfer_audit"
STRATEGIES = {
    "native_source", "source_materials", "visual_activation_partial",
}


class AITransferAuditError(ValueError):
    pass


def _load(path: Path, limit: int = 8 * 1024 * 1024) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise AITransferAuditError("Required local transfer receipt is unavailable.")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AITransferAuditError("Transfer receipt cannot be decoded.") from exc
    if not isinstance(value, dict):
        raise AITransferAuditError("Expected a transfer receipt object.")
    return value


def _same_sequence(package: object, observed: object) -> bool:
    """Allow only Unreal package path or matching same-name object path."""
    if not isinstance(package, str) or not isinstance(observed, str):
        return False
    match = re.fullmatch(r"(/Game/(?:[A-Za-z0-9_]+/)*([A-Za-z0-9_]+))", package)
    if not match:
        return False
    return observed in (package, package + "." + match.group(2))


def _safe_job(workspace: Path, job_id: str) -> tuple[dict, Path]:
    if not isinstance(job_id, str) or not JOB_ID.fullmatch(job_id):
        raise AITransferAuditError("Invalid local job identity.")
    root = workspace.resolve()
    job = _load(root / "jobs" / (job_id + ".json"))
    if job.get("job_id") != job_id:
        raise AITransferAuditError("Saved job identity differs from requested job.")
    candidate_id = job.get("candidate_id")
    if (not isinstance(candidate_id, str)
            or not re.fullmatch(r"[0-9A-Za-z_]{1,100}", candidate_id)):
        raise AITransferAuditError("Invalid transfer candidate identifier.")
    candidate = (root / "candidates" / candidate_id).resolve()
    if (candidate != Path(str(job.get("candidate_dir") or "")).resolve()
            or not candidate.is_relative_to((root / "candidates").resolve())):
        raise AITransferAuditError("Job candidate escapes the Studio workspace.")
    return job, candidate


def _decision(job: dict, candidate: Path) -> tuple[dict, dict, dict]:
    decision_file = candidate / "ai-conversion-decision.json"
    recorded_sha = job.get("ai_conversion_decision_sha256")
    if not isinstance(recorded_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", recorded_sha):
        raise AITransferAuditError("Job has no bound AI conversion decision hash.")
    if decision_file.is_symlink() or not decision_file.is_file():
        raise AITransferAuditError("Bound AI decision file is missing.")
    if hashlib.sha256(decision_file.read_bytes()).hexdigest() != recorded_sha:
        raise AITransferAuditError("AI decision bytes differ from approved queued job.")
    decision = _load(decision_file)
    if (decision.get("kind") != "cutsceneai.studio.ai_conversion_decision"
            or decision.get("schema_version") != "1"
            or decision.get("strategy") not in STRATEGIES
            or decision.get("model_invoked") is not True):
        raise AITransferAuditError("Expected a recorded model-selected conversion policy.")
    choices = decision.get("conversion_options")
    if (not isinstance(choices, dict)
            or set(choices) != {"enable_fbx_embedded_material_import",
                               "enable_actor_visibility_fallback"}
            or any(type(value) is not bool for value in choices.values())):
        raise AITransferAuditError("AI conversion options are not valid Boolean switches.")
    session = _load(candidate / "session.json")
    mapping_path = Path(str(job.get("mapping") or "")).resolve()
    # The generated candidate mapping is a sibling to its candidate folder.
    if mapping_path != candidate.with_suffix(".mapping.json"):
        raise AITransferAuditError("Conversion mapping is not the selected candidate copy.")
    mapping = _load(mapping_path)
    expected = session.get("target") or {}
    if (expected.get("mapping_path") != str(mapping_path)
            or expected.get("sequence_asset_path") != job.get("sequence_path")
            or hashlib.sha256(mapping_path.read_bytes()).hexdigest()
            != expected.get("mapping_sha256")):
        raise AITransferAuditError("Prepared mapping is stale or differs from session.")
    for key, enabled in choices.items():
        if bool(mapping.get(key)) != enabled:
            raise AITransferAuditError("Candidate mapping does not match AI policy: " + key)
    if decision["strategy"] == "visual_activation_partial" and not choices[
            "enable_actor_visibility_fallback"]:
        raise AITransferAuditError("Activation decision has no registered adapter enabled.")
    plan_path = candidate / "transfer-plan.json"
    plan = _load(plan_path)
    if not _same_sequence(job.get("sequence_path"), plan.get("sequence_asset_path")):
        raise AITransferAuditError("Prepared native plan is for a different Level Sequence.")
    return decision, plan, session


def _native_execution(job: dict, candidate: Path, plan: dict) -> dict[str, Any]:
    job_id = job["job_id"]
    receipt_path = candidate / ("unreal-runtime-receipt-" + job_id + ".json")
    result: dict[str, Any] = {
        "receipt_present": False,
        "native_builder_completed": False,
        "status": "NOT_EXECUTED_OR_NO_NATIVE_RECEIPT",
        "planned_action_count": len(plan.get("actions") or []),
        "native_planned_actions": None,
        "generated_sequence": False,
    }
    if not receipt_path.is_file():
        return result
    receipt = _load(receipt_path)
    result["receipt_present"] = True
    # The builder has its own independent CSIR-to-plan re-verification.
    if receipt.get("kind") != "cutsceneai.unreal.best_effort_receipt":
        raise AITransferAuditError("Unexpected native Unreal builder receipt.")
    if receipt.get("status") == "GENERATED_UNVERIFIED":
        if (receipt.get("transfer_plan_sha256")
                != hashlib.sha256(
                    (candidate / "transfer-plan.json").read_bytes()).hexdigest()
                or receipt.get("verified_level") != job.get("expected_level")
                or not _same_sequence(
                    job.get("sequence_path"), receipt.get("generated_sequence"))
        ):
            raise AITransferAuditError("Completed native Unreal receipt does not match plan or sequence.")
    # Early failures may lack a target project or a transfer-plan checksum.
    # They remain FAILED, not falsely counted as completed provenance.
    verified_project = receipt.get("verified_project")
    expected_project = job.get("expected_project")
    if isinstance(verified_project, str) and (
            not isinstance(expected_project, str)
            or Path(verified_project).resolve() != Path(expected_project).resolve()):
        raise AITransferAuditError("Unreal builder receipt has a different target project.")
    result["status"] = str(receipt.get("status") or "UNKNOWN")[:64]
    result["native_planned_actions"] = receipt.get("planned_actions")
    complete = (
        receipt.get("status") == "GENERATED_UNVERIFIED"
        and receipt.get("stage") == "complete"
        and job.get("generation_status") == "GENERATED_UNVERIFIED"
        and _same_sequence(job.get("sequence_path"), job.get("generated_sequence"))
    )
    result["native_builder_completed"] = bool(complete)
    result["generated_sequence"] = bool(complete)
    if complete:
        result["status"] = "GENERATED_UNVERIFIED"
    return result


def _cinetwin(job: dict, candidate: Path, session: dict) -> dict[str, Any]:
    output: dict[str, Any] = {
        "status": "NOT_MEASURED",
        "measurements_source_bound": False,
        "matched_characters_with_actor_frames": 0,
        "matched_characters_with_root_frames": 0,
        "max_actor_error_cm": None,
        "max_root_error_cm": None,
        "position_tolerance_cm": 2.0,
        "fidelity_verified": False,
    }
    requested = job.get("diagnostic_file")
    if not isinstance(requested, str) or not requested:
        return output
    report_path = Path(requested).resolve()
    if (report_path.parent != candidate or report_path.is_symlink()
            or not report_path.name.startswith("CineTwin_WorldPose_Diagnosis_")):
        raise AITransferAuditError("Native diagnostic is outside the exact transfer candidate.")
    report = _load(report_path)
    if (report.get("kind") != "cutsceneai.cinetwin.unreal_world_pose_diagnostic"
            or not _same_sequence(job.get("sequence_path"),
                                  (report.get("target") or {}).get("sequence_path"))):
        raise AITransferAuditError("Native CineTwin comparison targets a different sequence.")
    source = report.get("source") or {}
    expected = session.get("source") or {}
    expected_capture = session.get("source_capture") or {}
    if (source.get("csir_sha256") != expected.get("sha256")
            or source.get("capture_sha256") != expected_capture.get("sha256")):
        raise AITransferAuditError("CineTwin comparison uses different Unity source evidence.")
    target = report.get("target") or {}
    if (not isinstance(target.get("project"), str)
            or Path(target["project"]).resolve() != Path(job["expected_project"]).resolve()):
        raise AITransferAuditError("CineTwin comparison uses a different Unreal project.")
    if report.get("errors") or source.get("missing_source_frames"):
        output["status"] = "MEASUREMENTS_INCOMPLETE"
        return output
    max_actor: list[float] = []
    max_root: list[float] = []
    for entity in (report.get("entities") or {}).values():
        if not isinstance(entity, dict) or entity.get("status") != "READY":
            continue
        for key, target_list, count_key in (
            ("actor_world", max_actor, "matched_characters_with_actor_frames"),
            ("skeletal_root_world", max_root, "matched_characters_with_root_frames"),
        ):
            info = entity.get(key) or {}
            value = info.get("max_absolute_error_cm")
            if (type(value) in (float, int) and math.isfinite(value)
                    and value >= 0):
                target_list.append(float(value))
                output[count_key] += 1
    if not max_actor and not max_root:
        output["status"] = "NO_COMPARABLE_ENTITY_MEASUREMENTS"
    else:
        output["status"] = "MEASURED_NOT_FIDELITY_VERIFIED"
        output["max_actor_error_cm"] = max(max_actor) if max_actor else None
        output["max_root_error_cm"] = max(max_root) if max_root else None
        output["measurements_source_bound"] = True
    return output


def assess(workspace: str | Path, job_id: str) -> dict[str, Any]:
    """Public redacted summary; never print source paths or model secrets."""
    root = Path(workspace).resolve()
    job, candidate = _safe_job(root, job_id)
    base = {
        "kind": KIND,
        "job_id": job_id, "candidate_id": job["candidate_id"],
        "available": False,
        "status": "NO_AI_CONVERSION_DECISION",
        "fidelity_verified": False,
        "model_decision_recorded": False,
        "native_builder_completed": False,
    }
    if not job.get("ai_conversion_decision_sha256"):
        return base
    decision, plan, session = _decision(job, candidate)
    actions = plan.get("actions")
    if not isinstance(actions, list) or any(not isinstance(action, dict) for action in actions):
        raise AITransferAuditError("Prepared native plan has invalid action records.")
    native = _native_execution(job, candidate, plan)
    visibility_count = sum(action.get("kind") == "actor_visibility" for action in actions)
    if decision["conversion_options"]["enable_actor_visibility_fallback"] and not visibility_count:
        raise AITransferAuditError("AI selected activation approximation but no native action was planned.")
    # The original model's choice is a *recorded* choice, not proof that an
    # arbitrary material or animation conversion really happened.
    measured = _cinetwin(job, candidate, session) if native[
        "native_builder_completed"] else {
        "status": "NOT_MEASURED", "measurements_source_bound": False,
        "fidelity_verified": False,
    }
    state = (
        "AI_NATIVE_GENERATED_UNVERIFIED" if native["native_builder_completed"]
        else "AI_NATIVE_BLOCKED" if job.get("status") not in ("QUEUED", "RUNNING")
        else "AI_NATIVE_RUNNING" if job.get("status") == "RUNNING"
        else "AI_PLAN_QUEUED"
    )
    return {
        **base, "available": True, "status": state,
        "model_decision_recorded": True,
        "strategy": decision["strategy"],
        "reason": decision.get("reason", "")[:400],
        "conversion_options": decision["conversion_options"],
        "native_visibility_actions_planned": visibility_count,
        "plan_action_count": len(actions),
        "native_receipt_present": native["receipt_present"],
        "native_builder_completed": native["native_builder_completed"],
        "native_status": native["status"],
        "execution_stage": str(job.get("failure_stage") or job.get("execution_stage")
                               or "UNKNOWN")[:70],
        "cinetwin": measured,
        "fidelity_verified": False,
        "note": (
            "Model-selected policy and registered native actions are separate evidence. "
            "A generated sequence is not cross-engine cinematic fidelity."
        ),
    }
