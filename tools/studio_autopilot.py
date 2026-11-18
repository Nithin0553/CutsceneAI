"""Server-owned one-click Unity -> Unreal transfer lifecycle.

A click requests ONE new Unity snapshot and ONE new non-overwriting candidate.
Only existing, source-provenanced engine operations run; the AI may reason over
failures using the already guarded LangGraph strategy executor. The Studio can
close its browser without losing the transfer intent.
"""
from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import studio_project_discovery as discovery
import studio_unity_bridge as unity_bridge

_LOCK = threading.RLock()
ACTIVE = "autopilot-active.json"
STAGES = frozenset({
    "WAITING_FOR_UNITY", "WAITING_FOR_UNITY_CAPTURE", "CONNECTING",
    "ANALYZING_PROJECTS", "PREPARING",
    "WAITING_FOR_UNREAL", "UNREAL_RUNNING",
})
FINISHED = frozenset({"GENERATED_UNVERIFIED", "BLOCKED", "CANCELLED"})
# Native read-only character inspection must not wait forever on an orphaned
# editor request. Disconnects never authorize issuing a second native job.
NATIVE_PROBE_TIMEOUT_SECONDS = 180
# Manual Play Mode is explicitly requested; an orphaned request still needs an
# eventual safe terminal outcome without repeatedly creating capture tickets.
UNITY_CAPTURE_TIMEOUT_SECONDS = 3600
JOB_ID_RE = re.compile(r"[a-f0-9]{32}\Z")


class AutopilotError(ValueError):
    pass


def _load(path: Path) -> dict:
    obj = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(obj, dict):
        raise AutopilotError("Invalid Studio transfer state.")
    return obj


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        tmp.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def status(workspace: Path) -> dict[str, Any]:
    file = workspace / ACTIVE
    if not file.is_file() or file.is_symlink():
        return {"active": False, "status": "IDLE"}
    state = _load(file)
    # Never expose local snapshot bytes, agent keys or a transferable mapping.
    return {
        "active": True,
        "run_id": state.get("run_id"),
        "status": state.get("status"),
        "message": state.get("message", ""),
        "job_id": state.get("job_id", ""),
        "candidate_id": state.get("candidate_id", ""),
        "source_fidelity_verified": False,
        "fidelity_verified": False,
        "agent_enabled": True,
        "ai_conversion_strategy": state.get("ai_conversion_strategy", ""),
        "ai_animation_action": state.get("ai_animation_action", ""),
        "error": state.get("error", ""),
    }


def begin(workspace: Path, *, unity_folder: str, unreal_folder: str,
          unreal_project: str = "", source_rights_confirmed: bool,
          service: Any) -> dict[str, Any]:
    """Explicit Transfer click is consent to approved scoped editor operations."""
    with _LOCK:
        if source_rights_confirmed is not True:
            raise AutopilotError("Confirm that you have the rights to import Unity source assets.")
        existing = status(workspace)
        if existing["status"] in STAGES:
            raise AutopilotError("A transfer is already active; inspect it rather than submitting twice.")
        old_job = workspace / "active-job.json"
        if old_job.is_file():
            job_id = str(_load(old_job).get("job_id", ""))
            prior = service.job_status(job_id, workspace)
            if prior["status"] in {"QUEUED", "RUNNING"}:
                raise AutopilotError("The previous Unreal job is still running.")
        roots = discovery.project_roots(unity_folder, "unity")
        targets = discovery.project_roots(unreal_folder, "unreal")
        if len(roots) != 1 or len(targets) != 1:
            raise AutopilotError("Choose one real Unity project and one real Unreal project.")
        target = discovery.scan_unreal(
            targets[0], service.worker_connected(workspace),
            project_choice=unreal_project,
        )
        if not target["project"]:
            raise AutopilotError("Select one Unreal .uproject file, not an ambiguous project folder.")
        request = unity_bridge.request_snapshot(roots[0])
        record = {
            "kind": "cutsceneai.studio.autopilot",
            "schema_version": "1",
            "run_id": uuid.uuid4().hex,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "WAITING_FOR_UNITY",
            "message": "Waiting for Unity Editor to analyze the selected Timeline and source scene.",
            "source_request_id": request["request_id"],
            "unity_project": roots[0],
            "unreal_folder": targets[0],
            "unreal_project": target["project"],
            "source_rights_confirmed": True,
        }
        _write(workspace / ACTIVE, record)
        return {**status(workspace), "instruction": request["instruction"]}


def cancel(workspace: Path, *, service: Any) -> dict[str, Any]:
    """Stop before the first native job, without deleting immutable evidence.

    Never cancel a queued/running Unreal import: an interrupted engine write
    may already have changed staging assets or actor state.
    """
    with service.lock, _LOCK:
        path = workspace / ACTIVE
        if not path.is_file():
            return status(workspace)
        state = _load(path)
        if state["status"] == "CANCELLED":
            return status(workspace)
        active = workspace / "active-job.json"
        if active.is_file():
            identifier = str(_load(active).get("job_id") or "")
            if identifier:
                previous = service.job_status(identifier, workspace)
                if previous["status"] in {"QUEUED", "RUNNING"}:
                    raise AutopilotError(
                        "An Unreal transfer is queued or running; native import "
                        "cannot be interrupted safely. Inspect the job instead."
                    )
        if state["status"] == "UNREAL_RUNNING":
            raise AutopilotError(
                "Unreal execution has started; do not interrupt a partially imported candidate."
            )
        if state["status"] not in STAGES:
            raise AutopilotError("No pre-execution transfer is available to cancel.")
        state["status"] = "CANCELLED"
        state["message"] = (
            "Transfer cancelled before native execution. Existing Unity "
            "snapshots and prepared candidates were preserved."
        )
        state["error"] = ""
        _write(path, state)
        return status(workspace)


def _wait_timed_out(state: dict, timestamp_key: str, seconds: int) -> bool:
    started = state.get(timestamp_key)
    if not started:
        return False
    try:
        timestamp = datetime.fromisoformat(str(started))
    except ValueError as exc:
        raise AutopilotError("Studio wait timeout state is invalid.") from exc
    if timestamp.tzinfo is None:
        raise AutopilotError("Studio wait timeout is missing timezone.")
    elapsed = (datetime.now(timezone.utc) - timestamp).total_seconds()
    return elapsed > seconds


def _submitted_job(workspace: Path, candidate_id: str) -> str:
    """Recover ONLY an already persisted job from the same immutable candidate.

    A crash may happen after queue_trial writes jobs/<id>.json but before its
    result reaches autopilot-active.json. Never submit a second native write in
    that situation. Ambiguous or conflicting jobs require an explicit stop.
    """
    if not isinstance(candidate_id, str) or not candidate_id.isascii() or not candidate_id.replace("_", "").isalnum():
        raise AutopilotError("Invalid candidate identity during Unreal job recovery.")
    candidate_root = (workspace / "candidates").resolve()
    original_dir = workspace / "candidates" / candidate_id
    expected_dir = original_dir.resolve()
    if original_dir.is_symlink() or not expected_dir.is_relative_to(candidate_root):
        raise AutopilotError("Prepared candidate path is unsafe for native job recovery.")
    candidate_pointer = workspace / "active-candidate.json"
    if candidate_pointer.is_symlink() or not candidate_pointer.is_file():
        raise AutopilotError("Missing trusted active candidate for native job recovery.")
    if _load(candidate_pointer).get("candidate_id") != candidate_id:
        raise AutopilotError("Active candidate changed after the native job was submitted.")
    config = _load(workspace / "connection.json")
    session = _load(expected_dir / "session.json")
    if (session.get("source", {}).get("csir_path") != config.get("csir")
            or (session.get("source_capture") or {}).get("path") != config.get("capture")
            or session.get("target", {}).get("project_path") != config.get("target_project")):
        raise AutopilotError("Prepared session source or target changed during job recovery.")
    candidates = []
    jobs_dir = workspace / "jobs"
    for path in sorted(jobs_dir.glob("*.json")) if jobs_dir.is_dir() else ():
        if path.is_symlink():
            raise AutopilotError("Symlinked Unreal job evidence cannot be used for recovery.")
        job = _load(path)
        if job.get("candidate_id") != candidate_id:
            continue
        job_id = job.get("job_id")
        if (job.get("kind") != "cutsceneai.studio.local_unreal_job"
                or not isinstance(job_id, str) or not JOB_ID_RE.fullmatch(job_id)
                or path.stem != job_id
                or Path(str(job.get("candidate_dir") or "")).resolve() != expected_dir
                or job.get("csir") != config.get("csir")
                or job.get("capture") != config.get("capture")
                or job.get("expected_project") != config.get("target_project")
                or job.get("expected_level") != config.get("level_path")
                or job.get("sequence_path") != session.get("target", {}).get("sequence_asset_path")
                or job.get("mapping") != session.get("target", {}).get("mapping_path")):
            raise AutopilotError("Existing Unreal job identity disagrees with the prepared candidate.")
        candidates.append(job_id)
    if len(candidates) > 1:
        raise AutopilotError("Multiple jobs reference the same candidate; refusing unsafe replay.")
    active = workspace / "active-job.json"
    if active.is_symlink():
        raise AutopilotError("Symlinked active Unreal job pointer is unsafe.")
    if active.is_file():
        pointer = _load(active).get("job_id")
        if not candidates or pointer != candidates[0]:
            raise AutopilotError("Another Unreal job is active; refusing to queue or adopt a candidate.")
    if not candidates:
        return ""
    if not active.is_file():
        _write(active, {"job_id": candidates[0]})
    return candidates[0]


def _pick_level(record: dict, service: Any, workspace: Path) -> str:
    """Choose a proven active destination, never an arbitrary map in a project."""
    worker = service.worker_connected(workspace)
    inspected = discovery.scan_unreal(
        record["unreal_folder"], worker, project_choice=record["unreal_project"],
    )
    if inspected["project"] != record["unreal_project"]:
        raise AutopilotError("Unreal project identity changed during source analysis.")
    if inspected["new_level_required"]:
        return "/Game/CutSceneAI/AutoTransfer/L_Studio_Fresh"
    selected = inspected["active_level"]
    if worker.get("connected") and selected and selected in inspected["levels"]:
        return selected
    # Never choose one of multiple existing Unreal levels or modify an
    # arbitrary saved map without knowing which is open in the editor.
    return ""


def advance(workspace: Path, *, service: Any) -> dict[str, Any]:
    """Advance one durable stage without user clicks; safe to poll repeatedly."""
    with service.lock, _LOCK:
        file = workspace / ACTIVE
        if not file.is_file():
            return status(workspace)
        state = _load(file)
        phase = state["status"]
        if phase in FINISHED:
            return status(workspace)
        try:
            if phase == "WAITING_FOR_UNITY":
                source = unity_bridge.snapshot_status(
                    state["unity_project"], state["source_request_id"]
                )
                if source["status"] == "BLOCKED":
                    raise AutopilotError(source["reason"])
                if source["status"] == "SUCCEEDED":
                    state["csir_path"] = source["csir_path"]
                    state["census_path"] = source["census_path"]
                    request = unity_bridge.request_behavior_capture(
                        state["unity_project"], state["source_request_id"]
                    )
                    state["capture_request_id"] = request["request_id"]
                    state["capture_wait_started_at"] = datetime.now(timezone.utc).isoformat()
                    state["status"] = "WAITING_FOR_UNITY_CAPTURE"
                    state["message"] = request["instruction"]
            elif phase == "WAITING_FOR_UNITY_CAPTURE":
                observed = unity_bridge.behavior_capture_status(
                    state["unity_project"], state["capture_request_id"]
                )
                if observed["status"] == "BLOCKED":
                    raise AutopilotError(observed["reason"])
                if observed["status"] == "SUCCEEDED":
                    state.pop("capture_wait_started_at", None)
                    state["capture_path"] = observed["capture_path"]
                    state["status"] = "CONNECTING"
                    state["message"] = (
                        "Source CineTwin samples verified. Resolving native transfer mappings."
                    )
                else:
                    if _wait_timed_out(
                        state, "capture_wait_started_at", UNITY_CAPTURE_TIMEOUT_SECONDS,
                    ):
                        raise AutopilotError(
                            "Unity source CineTwin capture timed out after 60 minutes. "
                            "Check that the selected Unity Editor has the Studio Bridge "
                            "enabled and is in Play Mode; start a fresh transfer. "
                            "No Unreal candidate was submitted."
                        )
                    state["message"] = str(observed.get(
                        "message", "Waiting for saved Unity Play Mode behavior capture."
                    ))[:500]
            elif phase == "CONNECTING":
                level = _pick_level(state, service, workspace)
                if not level:
                    state["message"] = (
                        "Open the selected backed-up Unreal project and start its Studio "
                        "editor worker so CutSceneAI can identify the active destination map."
                    )
                else:
                    fields = discovery.build_connection(
                        state["unity_project"], state["unreal_folder"], state["csir_path"],
                        level, workspace=workspace,
                        worker=service.worker_connected(workspace),
                        unreal_project=state["unreal_project"],
                        source_rights_confirmed=True,
                    )
                    fields["capture"] = state["capture_path"]
                    connection = service.config_check(fields)
                    if (connection["csir"] != state["csir_path"]
                            or connection.get("capture") != state["capture_path"]):
                        raise AutopilotError("Unity source mapping changed during preparation.")
                    service.atomic_json(workspace / "connection.json", connection)
                    for name in ("active-candidate.json", "active-job.json",
                                 "attached-observation.json", "destination-readiness.json",
                                 "one-click-approval.json"):
                        (workspace / name).unlink(missing_ok=True)
                    state["status"] = "ANALYZING_PROJECTS"
                    state["message"] = "AI is analyzing verified Unity capture, source features and the connected Unreal destination."
            elif phase == "ANALYZING_PROJECTS":
                import studio_ui_features
                import studio_transfer_ai
                config = service.load_json(workspace / "connection.json")
                # The model cannot bypass source/census identity or partial
                # fidelity disclosures. Fail before creating a candidate.
                studio_ui_features.validate_options(config, {
                    "source_feature_surface_path": state["census_path"],
                    "require_complete_source_features": False,
                })
                worker = service.worker_connected(workspace)
                if not worker.get("connected"):
                    state["message"] = (
                        "Unreal disconnected during read-only AI project analysis. "
                        "Reconnect the same editor project and level; no native job "
                        "has been submitted."
                    )
                    _write(file, state)
                    return status(workspace)
                requested, probe = studio_transfer_ai.target_probe(config, worker, workspace, state["run_id"], write=_write)
                if requested and probe is None:
                    if _wait_timed_out(
                        state, "native_probe_wait_started_at", NATIVE_PROBE_TIMEOUT_SECONDS,
                    ):
                        raise AutopilotError(
                            "Native Unreal character inspection timed out after 180 seconds. "
                            "Inspect the editor worker and start a fresh transfer; "
                            "no AI decision or native candidate was created."
                        )
                    state.setdefault(
                        "native_probe_wait_started_at",
                        datetime.now(timezone.utc).isoformat(),
                    )
                    state["message"] = "Waiting for Unreal to inspect the mapped animation packages and approved rigs."
                    _write(file, state)
                    return status(workspace)
                state.pop("native_probe_wait_started_at", None)
                native_evidence = {"native_character_probe": probe} if probe is not None else {}
                decision = studio_transfer_ai.decide(
                    config, state["census_path"], worker, **native_evidence
                )
                character_report = decision.pop("character_compatibility", None)
                if character_report is not None:
                    policy = studio_transfer_ai.character_policy()
                    _write(workspace / policy.REPORT_FILE, character_report)
                    decision["character_probe_run_id"] = state["run_id"]
                _write(workspace / "ai-conversion-decision.json", decision)
                state["ai_conversion_strategy"] = decision["strategy"]
                state["ai_animation_action"] = (decision.get("animation_conversion") or {}).get("action_id", "")
                state["status"] = "PREPARING"
                state["message"] = (
                    "AI selected registered conversion strategy: "
                    + decision["strategy"] + ". Preparing immutable source-backed plan."
                )
                if state["ai_animation_action"]:
                    state["message"] = "AI selected an approved IK Retargeter for an evidence-matched in-place character."
            elif phase == "PREPARING":
                if (workspace / "active-candidate.json").exists():
                    raise AutopilotError(
                        "A candidate was already prepared before Studio restarted. "
                        "Inspect its immutable files; do not prepare or submit another candidate."
                    )
                import studio_ui_features
                # Validate the exact Unity-emitted census. Partial component
                # support is recorded, never misrepresented as full parity.
                import studio_transfer_ai
                config = service.load_json(workspace / "connection.json")
                decision = _load(workspace / "ai-conversion-decision.json")
                worker = service.worker_connected(workspace)
                if not worker.get("connected"):
                    state["message"] = (
                        "Unreal disconnected before immutable AI plan preparation. "
                        "Reconnect the same project; the approved model decision "
                        "is preserved and will be revalidated."
                    )
                    _write(file, state)
                    return status(workspace)
                native_evidence = {}
                character_report = None
                if decision.get("character_compatibility_sha256"):
                    policy = studio_transfer_ai.character_policy()
                    character_report = _load(workspace / policy.REPORT_FILE)
                    if policy.compatibility.digest(character_report) != decision["character_compatibility_sha256"]:
                        raise AutopilotError("Character report changed after the model selected a strategy.")
                    _, probe = studio_transfer_ai.target_probe(config, worker, workspace, state["run_id"])
                    native_evidence["native_character_probe"] = probe
                options = studio_transfer_ai.verify(
                    decision, config, state["census_path"], worker, **native_evidence,
                )
                audited = studio_ui_features.validate_options(
                    config,
                    {
                        "source_feature_surface_path": state["census_path"],
                        "require_complete_source_features": False,
                        **options,
                    },
                )
                animation = decision.get("animation_conversion")
                selection = {"character_selection": (character_report, animation)} if animation else {}
                candidate = service.prepare(workspace, audited, **selection)
                if character_report is not None:
                    _write(Path(candidate["candidate_dir"]) / policy.REPORT_FILE, character_report)
                _write(
                    Path(candidate["candidate_dir"]) / "ai-conversion-decision.json",
                    decision,
                )
                service.approve_one_click(
                    candidate["candidate_id"], workspace, enable_ai_agents=True
                )
                state["candidate_id"] = candidate["candidate_id"]
                state["status"] = "WAITING_FOR_UNREAL"
                state["message"] = "Plan ready. Waiting for the matching Unreal editor worker."
            elif phase == "WAITING_FOR_UNREAL":
                # Recover a previously submitted job BEFORE any destination probe
                # or queue attempt; a reboot may have lost only the UI transition.
                submitted = _submitted_job(workspace, state["candidate_id"])
                if submitted:
                    state["job_id"] = submitted
                    state["status"] = "UNREAL_RUNNING"
                    state["message"] = (
                        "Recovered the existing submitted Unreal job. "
                        "No new native work was queued."
                    )
                    _write(file, state)
                    return status(workspace)
                worker = service.worker_connected(workspace)
                if not worker.get("connected"):
                    state["message"] = "Open Unreal Editor and start its Studio worker to continue."
                else:
                    readiness = service.destination_readiness(workspace)
                    candidate = service.load_json(workspace / "active-candidate.json")
                    auto = candidate.get("automatic_setup") or {}
                    if auto.get("available") and auto.get("blockers"):
                        raise AutopilotError(
                            "Source asset import blocked: " + "; ".join(auto["blockers"][:5])
                        )
                    if readiness.get("status") in {
                        "WRONG_TARGET", "TARGET_EXISTS", "UPGRADE_COMPANION",
                        "INSPECTION_FAILED",
                    }:
                        raise AutopilotError(str(
                            readiness.get("next_action") or readiness["status"]
                        ))
                    # queue_trial performs its own final source, target, actor,
                    # readiness and no-overwrite checks before creating a job.
                    if (readiness.get("ready") or
                            (auto.get("available") and auto.get("ready")
                             and readiness.get("status") in {
                                 "READY", "NEW_LEVEL_REQUIRED",
                                 "SCENE_SETUP_REQUIRED", "ASSETS_REQUIRED",
                             })):
                        result = service.queue_trial(state["candidate_id"], workspace)
                        state["job_id"] = result["job_id"]
                        state["status"] = "UNREAL_RUNNING"
                        state["message"] = "Unreal is importing source assets and building the editable sequence."
                    else:
                        state["message"] = str(
                            readiness.get("next_action")
                            or "Waiting for native destination preflight."
                        )[:500]
            elif phase == "UNREAL_RUNNING":
                job = service.job_status(state["job_id"], workspace)
                if job["status"] not in {"RUNNING", "QUEUED"}:
                    if job.get("generation_status") == "GENERATED_UNVERIFIED":
                        state["status"] = "GENERATED_UNVERIFIED"
                        state["message"] = (
                            "Editable sequence generated. AI diagnostics and corrections "
                            "continue where registered capabilities permit; fidelity is not certified."
                        )
                    else:
                        state["status"] = "BLOCKED"
                        state["error"] = str(job.get("error") or job["status"])[:500]
                        state["message"] = "Native transfer stopped; original project evidence is preserved."
            else:
                raise AutopilotError("Unknown transfer lifecycle state.")
        except (ValueError, KeyError, OSError, RuntimeError, ImportError) as exc:
            state["status"] = "BLOCKED"
            state["message"] = "Transfer stopped safely; inspect the precise error."
            state["error"] = str(exc)[:700]
        _write(file, state)
        return status(workspace)


def start_daemon(workspace: Path, *, service: Any, interval: float = 2.0) -> threading.Event:
    stop = threading.Event()

    def run() -> None:
        while not stop.wait(interval):
            try:
                advance(workspace, service=service)
            except Exception:
                # The transfer state and last meaningful error remain durable.
                # Do not crash the localhost service because one run is invalid.
                pass

    threading.Thread(target=run, name="cutsceneai-autopilot", daemon=True).start()
    return stop
