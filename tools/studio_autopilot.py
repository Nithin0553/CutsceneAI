"""Server-owned one-click Unity -> Unreal transfer lifecycle.

A click requests ONE new Unity snapshot and ONE new non-overwriting candidate.
Only existing, source-provenanced engine operations run; the AI may reason over
failures using the already guarded LangGraph strategy executor. The Studio can
close its browser without losing the transfer intent.
"""
from __future__ import annotations

import json
import os
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
    "WAITING_FOR_UNITY", "CONNECTING", "PREPARING",
    "WAITING_FOR_UNREAL", "UNREAL_RUNNING",
})
FINISHED = frozenset({"GENERATED_UNVERIFIED", "BLOCKED"})


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
    with _LOCK:
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
                    state["status"] = "CONNECTING"
                    state["message"] = "Unity analyzed the Timeline. Resolving project mappings."
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
                    connection = service.config_check(fields)
                    if connection["csir"] != state["csir_path"]:
                        raise AutopilotError("Unity source mapping changed during preparation.")
                    service.atomic_json(workspace / "connection.json", connection)
                    for name in ("active-candidate.json", "active-job.json",
                                 "attached-observation.json", "destination-readiness.json",
                                 "one-click-approval.json"):
                        (workspace / name).unlink(missing_ok=True)
                    state["status"] = "PREPARING"
                    state["message"] = "Preparing source-provenanced assets and CED transfer plan."
            elif phase == "PREPARING":
                import studio_ui_features
                # Validate the exact Unity-emitted census. Partial component
                # support is recorded, never misrepresented as full parity.
                audited = studio_ui_features.validate_options(
                    service.load_json(workspace / "connection.json"),
                    {
                        "source_feature_surface_path": state["census_path"],
                        "require_complete_source_features": False,
                        "enable_fbx_embedded_material_import": True,
                    },
                )
                candidate = service.prepare(workspace, audited)
                service.approve_one_click(
                    candidate["candidate_id"], workspace, enable_ai_agents=True
                )
                state["candidate_id"] = candidate["candidate_id"]
                state["status"] = "WAITING_FOR_UNREAL"
                state["message"] = "Plan ready. Waiting for the matching Unreal editor worker."
            elif phase == "WAITING_FOR_UNREAL":
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
