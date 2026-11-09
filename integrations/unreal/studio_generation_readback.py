"""Read-only first-pass native verification after a successful Studio generation.

Captures evidence in the generating Unreal Editor, independently of Sequencer
plan values, without claiming editor restart or cross-engine fidelity.
Post-reopen audit remains a SEPARATE deliberate operation in a fresh process.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class GenerationReadbackError(ValueError):
    pass


def capture(workspace: str | Path, job: dict[str, Any], *, unreal_api: Any) -> dict[str, Any]:
    root = Path(workspace).resolve()
    job_id = str(job.get("job_id") or "")
    candidate_id = str(job.get("candidate_id") or "")
    if len(job_id) != 32 or any(c not in "0123456789abcdef" for c in job_id):
        raise GenerationReadbackError("Invalid generation job identifier.")
    if not candidate_id or not candidate_id.replace("_", "").isalnum():
        raise GenerationReadbackError("Invalid generation candidate identifier.")
    candidate = (root / "candidates" / candidate_id).resolve()
    if (candidate != Path(str(job.get("candidate_dir") or "")).resolve()
            or not candidate.is_relative_to((root / "candidates").resolve())):
        raise GenerationReadbackError("Unsafe candidate path or identity mismatch.")
    job_file = root / "jobs" / (job_id + ".json")
    stored = json.loads(job_file.read_text(encoding="utf-8-sig"))
    if (stored.get("job_id") != job_id
            or stored.get("candidate_id") != candidate_id
            or stored.get("sequence_path") != job.get("sequence_path")
            or stored.get("generation_status") != "GENERATED_UNVERIFIED"):
        raise GenerationReadbackError("Saved generation job is not the current completed sequence.")
    if not (candidate / "transfer-plan.json").is_file():
        raise GenerationReadbackError("Saved immutable transfer plan is missing.")
    if not job.get("receipt_file") or not Path(str(job["receipt_file"])).is_file():
        raise GenerationReadbackError("Native builder receipt is missing.")
    results: dict[str, Any] = {
        "kind": "cutsceneai.studio.generation_readback_summary",
        "job_id": job_id,
        "candidate_id": candidate_id,
        "generation_editor_only": True,
        "fidelity_verified": False,
        "restart_verified": False,
    }

    # Audit failure must never be silently counted as native proof. One
    # domain's exception does not prevent capturing the other domain.
    import studio_persistence_audit
    import studio_hierarchy_audit

    persistence_path = candidate / ("generation-readback-audit-" + job_id + ".json")
    try:
        if persistence_path.exists():
            raise GenerationReadbackError("Generation readback already exists; refusing overwrite.")
        report = studio_persistence_audit.audit(
            job_file, persistence_path, unreal_api=unreal_api,
        )
        results["native_structure"] = report.get("native_structure_status", "INCOMPLETE")
        results["native_structure_report"] = str(persistence_path)
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:
        results["native_structure"] = "INCOMPLETE"
        results["native_structure_error"] = str(exc)

    hierarchy_path = candidate / ("hierarchy-audit-" + job_id + "-generation.json")
    try:
        if hierarchy_path.exists():
            raise GenerationReadbackError("Generation hierarchy audit already exists; refusing overwrite.")
        report = studio_hierarchy_audit.audit(
            job_file, hierarchy_path, unreal_api=unreal_api,
        )
        results["source_hierarchy"] = report.get("status", "INCOMPLETE")
        results["source_hierarchy_report"] = str(hierarchy_path)
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:
        results["source_hierarchy"] = "INCOMPLETE"
        results["source_hierarchy_error"] = str(exc)
    return results
