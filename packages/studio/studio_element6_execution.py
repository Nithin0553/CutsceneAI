"""Element 6: durable, one-attempt guarded Unreal native job execution.

Pure Python / stdlib. The native worker calls this *before* mutating Unreal.
No AI commands, new native adapters, automatic retry or fidelity promotion.

A queued job may be claimed once across editor processes. If the process
crashes after the write-ahead claim, an orphan is *not* replayed: its exact
stage and incomplete evidence are exposed for manual inspection instead.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

KIND = "cutsceneai.studio.element6_native_attempt_claim"
RECEIPT_KIND = "cutsceneai.studio.element6_native_attempt_receipt"
VERSION = "1"
CANDIDATE = re.compile(r"[0-9]{8}T[0-9]{6}Z_[a-f0-9]{8}\Z")
JOB_ID = re.compile(r"[a-f0-9]{32}\Z")
SHA = re.compile(r"[a-f0-9]{64}\Z")
STAGES = (
    "CLAIMED_NO_REPLAY",
    "PREPARED_SOURCE_AND_ACTIONS_VERIFIED",
    "EDITOR_PREFLIGHT_COMPLETE",
    "DESTINATION_MUTATION_STARTED",
    "ASSET_AND_ACTOR_SETUP_COMPLETED",
    "NATIVE_SEQUENCE_BUILDER_STARTED",
    "NATIVE_SEQUENCE_BUILDER_RETURNED",
    "POST_GENERATION_DIAGNOSTICS_STARTED",
    "TERMINAL_EVIDENCE_RECORDED",
)
MUTATION_STAGE = "DESTINATION_MUTATION_STARTED"
MAX_JSON = 64 * 1024 * 1024
FINGERPRINT_FIELDS = (
    "kind", "schema_version", "job_id", "candidate_id", "candidate_dir",
    "csir", "capture", "mapping", "sequence_path", "expected_project",
    "expected_level", "create_level", "automatic_setup",
    "automatic_setup_manifest", "ai_agents_enabled",
    "ai_conversion_decision_sha256", "element_native_authorization_sha256",
)
FINAL_FAILURE_STATES = {
    "BLOCKED_OR_FAILED", "PARTIAL_SETUP_MUST_INSPECT",
    "BLOCKED_SETUP", "SETUP_SAVED_BUT_NOT_READY",
    "GENERATED_ANIMATION_VERIFICATION_FAILED_REVIEW_REQUIRED",
    "GENERATED_LEVEL_NOT_SAVED_REVIEW_REQUIRED",
}


class GuardedExecutionError(ValueError):
    """The editor must not run or replay an unsafe native job."""


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _read(path: Path) -> dict:
    if (path.is_symlink() or not path.is_file()
            or not 0 < path.stat().st_size <= MAX_JSON):
        raise GuardedExecutionError("Guarded native record is unsafe or missing.")
    try:
        body = json.loads(path.read_text(encoding="utf-8-sig"))
    except (UnicodeError, ValueError) as exc:
        raise GuardedExecutionError("Guarded native record is not valid JSON.") from exc
    if not isinstance(body, dict):
        raise GuardedExecutionError("Guarded native record must be an object.")
    return body


def _sha(path: Path) -> str:
    _read(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_once(path: Path, body: dict) -> None:
    """Durable exclusive claim, including a directory fsync when supported."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(body, handle, sort_keys=True, ensure_ascii=False,
                      allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise GuardedExecutionError(
            "Native job already claimed; interrupted or completed attempts cannot replay."
        ) from exc
    if os.name != "nt":
        try:
            fd = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError:
            pass


def _identity(job: dict) -> dict:
    return {field: job.get(field) for field in FINGERPRINT_FIELDS}


def _paths(workspace: Path, job: dict) -> tuple[Path, Path]:
    if (not isinstance(job, dict)
            or job.get("kind") != "cutsceneai.studio.local_unreal_job"
            or job.get("schema_version") != "0.1.0"
            or not isinstance(job.get("job_id"), str)
            or not JOB_ID.fullmatch(job["job_id"])
            or not isinstance(job.get("candidate_id"), str)
            or not CANDIDATE.fullmatch(job["candidate_id"])):
        raise GuardedExecutionError("Native job identity or schema is invalid.")
    root = (workspace / "candidates").resolve()
    candidate = root / job["candidate_id"]
    if (candidate.is_symlink() or not candidate.is_dir()
            or candidate.resolve().parent != root
            or candidate.resolve() != Path(str(
                job.get("candidate_dir") or ""
            )).resolve()):
        raise GuardedExecutionError("Native job is not in its prepared candidate directory.")
    jobs = workspace / "jobs"
    if jobs.is_symlink() or not jobs.is_dir():
        raise GuardedExecutionError("Native queue directory is unsafe.")
    job_path = jobs / (job["job_id"] + ".json")
    if job_path.is_symlink():
        raise GuardedExecutionError("Native job file is a symlink.")
    return candidate, job_path


def _inputs(workspace: Path, job: dict, *, queued: bool) -> tuple[Path, dict, dict]:
    candidate, job_path = _paths(workspace, job)
    stored = _read(job_path)
    if stored != job:
        raise GuardedExecutionError("Loaded native queue payload no longer matches disk.")
    if queued and job.get("status") != "QUEUED":
        raise GuardedExecutionError("Native job is not queued for its first attempt.")
    active = _read(workspace / "active-job.json")
    if (set(active) != {"job_id"} or active["job_id"] != job["job_id"]):
        raise GuardedExecutionError(
            "Native execution is limited to the currently selected active job."
        )
    candidate_active = _read(workspace / "active-candidate.json")
    if candidate_active.get("candidate_id") != job["candidate_id"]:
        raise GuardedExecutionError("Active Studio candidate has changed since submission.")
    session = _read(candidate / "session.json")
    if (session.get("kind") != "cutsceneai.studio.prepared_transfer"
            or session.get("source", {}).get("csir_path") != job.get("csir")
            or session.get("target", {}).get("mapping_path") != job.get("mapping")
            or session.get("target", {}).get("sequence_asset_path")
            != job.get("sequence_path")
            or (session.get("target", {}).get("project_path") is not None
                and os.path.normcase(str(Path(
                    session["target"]["project_path"]
                ).resolve())) != os.path.normcase(str(
                    Path(job["expected_project"]).resolve()
                )))):
        raise GuardedExecutionError("Native job does not match immutable session identity.")
    sequence = job.get("sequence_path")
    if (type(sequence) is not str or not sequence.startswith("/Game/")
            or not sequence.rstrip("/").split("/")[-1]
            or ".." in sequence.split("/")):
        raise GuardedExecutionError("Native destination sequence is invalid.")
    expected_level = job.get("expected_level")
    if (type(expected_level) is not str or not expected_level.startswith("/Game/")):
        raise GuardedExecutionError("Native target level is missing.")
    for field in ("ai_conversion_decision_sha256",
                  "element_native_authorization_sha256"):
        value = job.get(field) or ""
        if not isinstance(value, str) or (value and not SHA.fullmatch(value)):
            raise GuardedExecutionError("Invalid immutable native approval fingerprint.")
    for source_key in ("csir", "mapping"):
        f = Path(str(job.get(source_key) or ""))
        if f.is_symlink():
            raise GuardedExecutionError("Native source evidence is a symlink.")
    if (candidate / "transfer-plan.json").is_symlink():
        raise GuardedExecutionError("Prepared native plan is a symlink.")
    return candidate, session, stored


def _fingerprints(candidate: Path, job: dict) -> dict:
    result = {
        "source_csir_file_sha256": _sha(Path(job["csir"])),
        "target_mapping_file_sha256": _sha(Path(job["mapping"])),
        "prepared_plan_file_sha256": _sha(candidate / "transfer-plan.json"),
        "prepared_session_file_sha256": _sha(candidate / "session.json"),
    }
    review = candidate / "element-workflow-active.json"
    if review.exists():
        result["element_review_pointer_file_sha256"] = _sha(review)
    if job.get("element_native_authorization_sha256"):
        grant = _read(candidate / "element-native-approval.json")
        if grant.get("authorization_sha256") != job[
            "element_native_authorization_sha256"
        ]:
            raise GuardedExecutionError("Native job approval no longer matches candidate.")
        result["native_approval_file_sha256"] = _sha(
            candidate / "element-native-approval.json"
        )
    if job.get("ai_conversion_decision_sha256"):
        path = candidate / "ai-conversion-decision.json"
        if _sha(path) != job["ai_conversion_decision_sha256"]:
            raise GuardedExecutionError("AI conversion decision no longer matches candidate.")
        result["ai_decision_file_sha256"] = job["ai_conversion_decision_sha256"]
    return result


def _claim_path(candidate: Path, job_id: str) -> Path:
    return candidate / ("element6-native-claim-" + job_id + ".json")


def _receipt_path(candidate: Path, job_id: str) -> Path:
    return candidate / ("element6-native-receipt-" + job_id + ".json")


def claim(workspace: Path, job: dict, *, editor_pid: int) -> dict:
    """Acquire a durable once-only claim before any editor mutation.

    A crash after claiming is deliberately treated as a potentially
    partially changed scene, even if the last checkpoint was preflight.
    """
    if type(editor_pid) is not int or editor_pid <= 0:
        raise GuardedExecutionError("Native editor process identity is invalid.")
    workspace = Path(workspace)
    candidate, _session, stored = _inputs(workspace, job, queued=True)
    fingerprint = _fingerprints(candidate, job)
    record = {
        "kind": KIND, "schema_version": VERSION,
        "job_id": job["job_id"], "candidate_id": job["candidate_id"],
        "editor_pid": editor_pid,
        "queued_job_sha256": digest(stored),
        "immutable_job_identity_sha256": digest(_identity(job)),
        "source_and_prepared_evidence": fingerprint,
        "native_attempt_index": 1,
        "claim_scope": "SINGLE_ENGINE_ATTEMPT_NO_AUTOMATIC_REPLAY",
        "native_actions_executed": False,
        "native_readback_verified": False,
        "full_cutscene_fidelity_verified": False,
    }
    record["claim_sha256"] = digest(record)
    _write_once(_claim_path(candidate, job["job_id"]), record)
    return record


def verify_claim(workspace: Path, job: dict, claim_record: dict) -> None:
    """Bind the live worker to its unmodified original queued evidence."""
    workspace = Path(workspace)
    candidate, _job_path = _paths(workspace, job)
    actual = _read(_claim_path(candidate, job["job_id"]))
    if (not isinstance(claim_record, dict) or actual != claim_record
            or claim_record.get("kind") != KIND
            or claim_record.get("schema_version") != VERSION
            or claim_record.get("claim_sha256") != digest({
                key: value for key, value in claim_record.items()
                if key != "claim_sha256"
            })
            or claim_record.get("immutable_job_identity_sha256")
            != digest(_identity(job))
            or claim_record.get("native_attempt_index") != 1
            or claim_record.get("claim_scope")
            != "SINGLE_ENGINE_ATTEMPT_NO_AUTOMATIC_REPLAY"
            or claim_record.get("native_actions_executed") is not False
            or claim_record.get("full_cutscene_fidelity_verified") is not False
            or claim_record.get("source_and_prepared_evidence")
            != _fingerprints(candidate, job)):
        raise GuardedExecutionError(
            "Claimed native attempt or its original source/action evidence changed."
        )
    active = _read(workspace / "active-job.json")
    if active.get("job_id") != job["job_id"]:
        raise GuardedExecutionError("Native attempt lost active-job ownership.")


def step(workspace: Path, job: dict, claim_record: dict, stage: str) -> dict:
    """Append a strictly ordered, unique stage checkpoint (no raw source names)."""
    if stage not in STAGES or stage == STAGES[0]:
        raise GuardedExecutionError("Unrecognized guarded native execution stage.")
    verify_claim(workspace, job, claim_record)
    candidate, _ = _paths(Path(workspace), job)
    prefix = "element6-native-stage-" + job["job_id"] + "-"
    for index, stage_name in enumerate(STAGES[1:], 1):
        path = candidate / f"{prefix}{index:02d}.json"
        if path.exists():
            record = _read(path)
            if (record.get("stage") != stage_name
                    or record.get("claim_sha256") != claim_record["claim_sha256"]
                    or record.get("stage_index") != index
                    or record.get("stage_sha256") != digest({
                        k: v for k, v in record.items() if k != "stage_sha256"
                    })):
                raise GuardedExecutionError("Guarded native execution stage ledger altered.")
        elif index < STAGES.index(stage):
            raise GuardedExecutionError("Execution stage ledger has missing earlier checkpoint.")
    index = STAGES.index(stage)
    existing = candidate / f"{prefix}{index:02d}.json"
    if existing.exists():
        raise GuardedExecutionError("Native execution stage cannot be repeated or replayed.")
    record = {
        "kind": "cutsceneai.studio.element6_execution_stage",
        "job_id": job["job_id"], "candidate_id": job["candidate_id"],
        "claim_sha256": claim_record["claim_sha256"],
        "stage": stage, "stage_index": index,
        "native_readback_verified": False,
        "full_cutscene_fidelity_verified": False,
    }
    record["stage_sha256"] = digest(record)
    _write_once(existing, record)
    return record


def terminal(workspace: Path, job: dict, claim_record: dict) -> dict:
    """A completed builder receipt is not individual-action readback/fidelity."""
    candidate, _ = _paths(Path(workspace), job)
    active_claim = _read(_claim_path(candidate, job["job_id"]))
    if (active_claim != claim_record
            or active_claim.get("claim_sha256") != digest({
                key: value for key, value in active_claim.items()
                if key != "claim_sha256"
            })):
        raise GuardedExecutionError("Cannot finalize an altered native attempt.")
    receipt_file = candidate / ("unreal-runtime-receipt-" + job["job_id"] + ".json")
    successful = False
    native_receipt_sha = None
    if receipt_file.exists():
        runtime = _read(receipt_file)
        native_receipt_sha = _sha(receipt_file)
        successful = (
            runtime.get("kind") == "cutsceneai.unreal.best_effort_receipt"
            and runtime.get("status") == "GENERATED_UNVERIFIED"
            and runtime.get("stage") == "complete"
            and runtime.get("transfer_plan_sha256")
            == claim_record["source_and_prepared_evidence"][
                "prepared_plan_file_sha256"
            ]
        )
    if job.get("status") in FINAL_FAILURE_STATES or job.get(
        "generation_status"
    ) != "GENERATED_UNVERIFIED":
        successful = False
    result = {
        "kind": RECEIPT_KIND,
        "schema_version": VERSION,
        "job_id": job["job_id"], "candidate_id": job["candidate_id"],
        "claim_sha256": claim_record["claim_sha256"],
        "immutable_job_identity_sha256":
            claim_record["immutable_job_identity_sha256"],
        "runtime_receipt_sha256": native_receipt_sha,
        "status": (
            "NATIVE_BUILDER_COMPLETED_READBACK_AND_FIDELITY_UNVERIFIED"
            if successful else "INCOMPLETE_OR_FAILED_NO_AUTOMATIC_REPLAY"
        ),
        "native_attempt_index": 1,
        "requires_manual_inspection": not successful,
        "native_builder_completed": successful,
        "individual_native_action_readbacks_verified": False,
        "full_cutscene_fidelity_verified": False,
    }
    result["receipt_sha256"] = digest(result)
    _write_once(_receipt_path(candidate, job["job_id"]), result)
    return result


def inspect(workspace: Path, job: dict) -> dict:
    """Read-only durable state for Studio UI; no replay and no native claims."""
    candidate, _ = _paths(Path(workspace), job)
    claim_path = _claim_path(candidate, job["job_id"])
    if not claim_path.exists():
        return {"available": False, "status": "NOT_CLAIMED",
                "native_replay_allowed": False,
                "full_cutscene_fidelity_verified": False}
    record = _read(claim_path)
    if (record.get("kind") != KIND
            or record.get("claim_sha256") != digest({
                k: v for k, v in record.items() if k != "claim_sha256"
            })
            or record.get("job_id") != job["job_id"]
            or record.get("candidate_id") != job["candidate_id"]):
        raise GuardedExecutionError("Existing native claim cannot be trusted.")
    stages = []
    prefix = "element6-native-stage-" + job["job_id"] + "-"
    gap = False
    for index, stage in enumerate(STAGES[1:], 1):
        file = candidate / f"{prefix}{index:02d}.json"
        if not file.exists():
            gap = True
            continue
        if gap:
            raise GuardedExecutionError("Native stage ledger skipped a checkpoint.")
        doc = _read(file)
        if (doc.get("stage") != stage
                or doc.get("stage_index") != index
                or doc.get("claim_sha256") != record["claim_sha256"]
                or doc.get("stage_sha256") != digest({
                    k: v for k, v in doc.items() if k != "stage_sha256"
                })):
            raise GuardedExecutionError("Native stage ledger does not match original claim.")
        stages.append(stage)
    receipt_path = _receipt_path(candidate, job["job_id"])
    status = "ATTEMPT_IN_PROGRESS_OR_INTERRUPTED_INSPECT_BEFORE_ANY_RECOVERY"
    terminal_state = None
    if receipt_path.exists():
        receipt = _read(receipt_path)
        if (receipt.get("kind") != RECEIPT_KIND
                or receipt.get("claim_sha256") != record["claim_sha256"]
                or receipt.get("job_id") != job["job_id"]
                or receipt.get("receipt_sha256") != digest({
                    k: v for k, v in receipt.items() if k != "receipt_sha256"
                })):
            raise GuardedExecutionError("Native attempt receipt is invalid.")
        status = receipt["status"]
        terminal_state = receipt["requires_manual_inspection"]
    return {
        "available": True, "status": status,
        "editor_pid": record["editor_pid"],
        "claim_sha256": record["claim_sha256"],
        "stages": stages, "last_stage": stages[-1] if stages else STAGES[0],
        "native_replay_allowed": False,
        "requires_manual_inspection": terminal_state,
        "native_builder_completed": status.startswith("NATIVE_BUILDER_COMPLETED_"),
        "full_cutscene_fidelity_verified": False,
    }
