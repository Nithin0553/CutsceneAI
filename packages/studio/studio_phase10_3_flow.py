"""Read-only Stage 1–9 diagnostics shared by default and advanced Studio UIs.

Never infer native proof, source equivalence, or recovery permission from a
Stage 6 generated status. The current autopilot run owns any job displayed.
"""
from __future__ import annotations

import re
from typing import Any

JOB_ID = re.compile(r"[a-f0-9]{32}\Z")
NAMES = (
    ("unity_evidence", "Unity source and CineTwin"),
    ("ced", "CED knowledge retrieval"),
    ("ai_plan", "AI conversion planning"),
    ("validate", "Strategy validation"),
    ("compile", "Source-bound conversion plan"),
    ("native", "Guarded Unreal execution"),
    ("readback", "Native CineTwin readback"),
    ("repair", "Bounded repairs"),
    ("outcome", "Final source report"),
)
MILESTONES = {
    "WAITING_FOR_UNITY": 0,
    "WAITING_FOR_UNITY_CAPTURE": 0,
    "CONNECTING": 1,
    "ANALYZING_PROJECTS": 2,
    "WAITING_FOR_MODEL": 2,
    "PREPARING": 4,
    "WAITING_FOR_UNREAL": 5,
    "UNREAL_RUNNING": 5,
    "GENERATED_UNVERIFIED": 6,
    "BLOCKED": -1,
    "CANCELLED": -1,
    "IDLE": -1,
}
STAGE_HINTS = (
    "Select a Unity Timeline and record original source and Play Mode samples.",
    "Retrieve CED capability knowledge for every original source occurrence.",
    "Inspect the model/provider and source-bound conversion alternatives.",
    "Validate the selected strategy and reject unsupported conversions.",
    "Review the compiled actions, source fingerprints and destination mapping.",
    "Inspect the exact native job, staged assets and saved Unreal sequence.",
    "Capture the saved target sequence in an independent Unreal Editor process.",
    "Review bounded repair consent, native readback and rollback status.",
    "Review every source element and remaining fidelity limitations.",
)


def summarize(snapshot: dict[str, Any], run: dict[str, Any],
              job: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return safe guidance, never paths, engine commands or privileged claims."""
    if not isinstance(snapshot, dict) or not isinstance(run, dict):
        raise ValueError("Studio status and autopilot evidence required.")
    if job is not None and not isinstance(job, dict):
        raise ValueError("Invalid current job evidence.")
    run_status = str(run.get("status") or "IDLE")
    if run_status not in MILESTONES:
        run_status = "BLOCKED"
    current_id = str(snapshot.get("active_job") or "")
    run_id = str(run.get("job_id") or "")
    has_run = run.get("active") is True
    # A new blocked/cancelled/waiting run must never inherit an earlier
    # terminal native job's identity or source findings.
    same_job = bool(
        current_id and JOB_ID.fullmatch(current_id)
        and job and job.get("job_id") == current_id
        and (not has_run or run_id == current_id)
    )
    native_status = str(job.get("status") or "") if same_job else ""
    candidate = snapshot.get("candidate") or {}
    has_candidate = (isinstance(candidate, dict)
                     and bool(candidate.get("candidate_id"))
                     and (not has_run or candidate.get("candidate_id") ==
                          run.get("candidate_id")))
    worker = snapshot.get("unreal_worker") or {}
    unity = snapshot.get("unity_editor") or {}
    destination = snapshot.get("destination_readiness") or {}
    issues = []
    if not snapshot.get("connection") and run_status not in (
            "WAITING_FOR_UNITY", "WAITING_FOR_UNITY_CAPTURE", "CONNECTING"):
        issues.append("Connect the exact Unity and Unreal projects.")
    if unity.get("connected") is not True:
        issues.append(str(unity.get("next_action") or
                          "Enable the Unity source companion in the selected project.")[:260])
    if worker.get("connected") is not True:
        issues.append("Connect the matching Unreal Editor companion; do not restart or retry a native job.")
    if destination.get("ready") is not True:
        hint = destination.get("next_action")
        if isinstance(hint, str) and hint:
            issues.append(hint[:260])
    if run_status in {"BLOCKED", "CANCELLED"}:
        issues.append(str(run.get("recovery_action") or
                          "Inspect the last durable evidence and explicitly start a new transfer.")[:260])
    native_submitted = bool(
        same_job or (has_run and (run_status == "UNREAL_RUNNING" or run_id))
    )
    retry_allowed = False  # Never grant native replay through a diagnostic.
    progress = MILESTONES[run_status]
    if has_candidate and progress < 4 and run_status not in {"BLOCKED", "CANCELLED"}:
        progress = 4
    if same_job and run_status not in {"BLOCKED", "CANCELLED"}:
        progress = max(progress, 5)
    stages = []
    for index, (key, label) in enumerate(NAMES):
        if run_status == "BLOCKED" and index == max(0, min(8, int(run.get(
                "last_completed_stage_index", 0)))):
            state = "BLOCKED"
        elif run_status == "CANCELLED" and index == 5:
            state = "CANCELLED_BEFORE_NATIVE_OR_MANUAL_INSPECTION"
        elif index < progress:
            state = "PROGRESSED_SOURCE_ONLY"
        elif index == progress:
            state = "ACTIVE_OR_PENDING"
        else:
            state = "NOT_VERIFIED"
        if index == 5 and same_job:
            state = "GENERATED_BUT_FIDELITY_UNVERIFIED" if (
                job.get("generation_status") == "GENERATED_UNVERIFIED"
            ) else "NATIVE_JOB_REQUIRES_INSPECTION"
        stages.append({
            "id": index + 1, "key": key, "label": label,
            "status": state, "next_action": STAGE_HINTS[index],
            "native_or_rendered_fidelity_verified": False,
        })
    return {
        "kind": "cutsceneai.studio.phase10_3.flow_diagnostics",
        "schema_version": "1",
        "autopilot_status": run_status,
        "native_job_identity_matches_current_run": same_job,
        "native_status": native_status if same_job else "NOT_CURRENT",
        "native_submitted_or_uncertain": native_submitted,
        "native_replay_authorized": retry_allowed,
        "source_and_native_full_fidelity_verified": False,
        "stages": stages,
        "issues": list(dict.fromkeys(issues))[:5],
        "next_action": (
            str(run.get("recovery_action"))[:260]
            if run_status == "BLOCKED" and run.get("recovery_action")
            else (issues[0] if issues else STAGE_HINTS[max(0, min(progress, 8))])
        ),
    }
