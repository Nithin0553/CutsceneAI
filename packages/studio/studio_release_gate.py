"""Fail-closed release assessment from inspected, source-bound Studio evidence.

This is an independent gate, not the converter or an LLM. A green Unreal
generation alone can never satisfy the source-target fidelity requirements.
Release readiness is a result of independently verified domains, not marketing
labels, local CI, or the number of repair attempts.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


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

    # Verified source provenance is a prerequisite to all downstream claims.
    csir_path = Path(str(job.get("csir") or "")).resolve()
    plan_path = candidate / "transfer-plan.json"
    if not csir_path.is_file() or not plan_path.is_file():
        record("source_and_plan", "INCOMPLETE",
               "Unity CSIR source and immutable transfer plan must both exist.")
    else:
        plan = _read(plan_path)
        record(
            "source_and_plan",
            "PASS" if plan.get("sequence_asset_path") == job.get("sequence_path")
            else "FAIL",
            "Existing Unity source and plan observed; their sequence identity must match.",
            csir_sha256=_sha(csir_path),
            plan_sha256=_sha(plan_path),
        )

    generation = job.get("generation_status") == "GENERATED_UNVERIFIED"
    record(
        "native_generation", "PASS" if generation else
        "INCOMPLETE" if job.get("status") in {"QUEUED", "RUNNING"} else "FAIL",
        "Editable Unreal sequence generation; PASS does not imply cinematic fidelity.",
        generated_sequence=job.get("generated_sequence"),
    )

    persistence = _latest(
        candidate, "post-reopen-audit-" + job_id + ".json",
        "cutsceneai.studio.persistence_audit", job,
    )
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
               "PASS" if persistence.get("restart_verified") is True else "INCOMPLETE",
               "A same-session snapshot cannot certify reopen persistence.")

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
        record("native_visual_prerequisites",
               "FAIL" if issues else "PASS",
               "Target scene prerequisites, not Unity/Unreal rendered-frame equivalence.",
               findings=issues,
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
