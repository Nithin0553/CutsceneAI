"""Strictly read-only release gate for one AI-guided Studio transfer.

An AI decision, mocked tests, native generation, or a different-editor process
alone cannot certify a visually matching cinematic. The gate separates the
automatically measured subset from untested rendering/audio/behavior domains.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import studio_ai_transfer_audit as audit


def _read(path: Path, *, limit: int = 16 * 1024 * 1024) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError("Missing, unsafe, or oversized release evidence.")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Malformed release evidence.") from exc
    if not isinstance(data, dict):
        raise ValueError("Expected a release evidence object.")
    return data


def _sha(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Missing source-bound release evidence.")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(data)
    return digest.hexdigest()


def _reopened(candidate: Path, job: dict) -> dict[str, Any]:
    folders = sorted(path for path in candidate.glob("native-acceptance-*")
                     if path.is_dir() and not path.is_symlink()
                     and path.resolve().parent == candidate)
    result = {"passed": False, "status": "REOPENED_EDITOR_ACCEPTANCE_NOT_RECORDED"}
    for folder in reversed(folders):
        comparison_file = folder / "comparison.json"
        persistence_file = folder / "persistence.json"
        observation_file = folder / "target-behavior.json"
        sampling_file = folder / "sampling-plan.json"
        if not comparison_file.exists():
            continue
        comparison = _read(comparison_file)
        native = _read(persistence_file)
        identity = job["job_id"]
        if (comparison.get("job_id") != identity
                or native.get("kind") != "cutsceneai.studio.persistence_audit"
                or native.get("expected_project") != job.get("expected_project")
                or native.get("expected_level") != job.get("expected_level")
                or native.get("status") != comparison.get("native_persistence_status")
                or comparison.get("persistence_sha256") != _sha(persistence_file)
                or comparison.get("target_observation_sha256") != _sha(observation_file)
                or comparison.get("sampling_plan_sha256") != _sha(sampling_file)
                or comparison.get("source_capture_sha256") != _sha(Path(job["capture"]))):
            raise ValueError("Reopened native acceptance evidence does not belong to this job.")
        generated = comparison.get("generation_editor_pid")
        observed = comparison.get("observation_editor_pid")
        separate_process = (
            type(generated) is int and generated > 0
            and type(observed) is int and observed > 0
            and generated != observed
            and generated == job.get("generation_editor_pid")
        )
        good = bool(
            separate_process
            and comparison.get("acceptance_status")
            == "STRUCTURE_AND_MEASURED_MOTION_WITHIN_TOLERANCE"
            and native.get("restart_verified") is True
            and native.get("native_structure_status") == "PASS"
            and native.get("provenance_status") == "COMPLETE"
            and native.get("status") == "STRUCTURAL_READBACK_PASS_DIFFERENT_EDITOR_PROCESS"
        )
        if job.get("character_native_readback_status") == "PASS":
            character = comparison.get("character_conversion") or {}
            good = good and (
                character.get("reopened_character_readback_status") == "PASS"
                and character.get("action_id") == "use_approved_ik_retarget_profile"
            )
        return {
            "passed": bool(good),
            "status": ("MEASURED_STRUCTURE_AND_MOTION_PASS" if good
                       else "REOPENED_ENGINE_ACCEPTANCE_INCOMPLETE"),
            "separate_editor_process": separate_process,
        }
    return result


def assess(workspace: str | Path, job_id: str) -> dict[str, Any]:
    """Never equate structural/motion subset with complete cinematic parity."""
    root = Path(workspace).resolve()
    if not isinstance(job_id, str) or not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise ValueError("Invalid release job identifier.")
    job, candidate = audit._safe_job(root, job_id)
    outcome = audit.assess(root, job_id)
    incomplete = []
    if not outcome.get("model_decision_recorded"):
        incomplete.append("A source-bound pre-transfer AI conversion decision is missing.")
    elif not outcome.get("native_builder_completed"):
        incomplete.append("Native Unreal sequence generation is not confirmed by its receipt.")
    character = outcome.get("character_conversion") or {}
    if character.get("selected") and not character.get("native_readback_passed"):
        incomplete.append("Approved IK retarget native skeleton/clip readback did not pass.")
    opened = {"passed": False, "status": "REOPENED_EDITOR_ACCEPTANCE_NOT_RECORDED"}
    if outcome.get("native_builder_completed"):
        opened = _reopened(candidate, job)
    if not opened["passed"]:
        incomplete.append("Independent Unreal reopen and source-matched temporal comparison not complete.")
    # No currently deployed framework can certify all visual, audio, VFX,
    # scripting, physics, lighting, or subjective cinematic fidelity.
    # These are explicit release blockers even with perfect measured motion.
    incomplete.extend([
        "Rendered camera, lighting, materials and visual appearance require review.",
        "Audio, events, physics, animation layers and unsupported semantics require review.",
        "Human acceptance of a representative cutscene matrix is not recorded.",
    ])
    return {
        "kind": "cutsceneai.studio.release_readiness",
        "job_id": job_id,
        "status": ("MEASURED_SCOPE_READY_HUMAN_REVIEW_REQUIRED" if opened["passed"]
                   else "ENGINE_ACCEPTANCE_PENDING"),
        "code_only_acceptance_completed": False,
        "automated_native_scope_passed": bool(opened["passed"]),
        "native_measurement": opened,
        "native_builder_completed": bool(outcome.get("native_builder_completed")),
        "model_decision_recorded": bool(outcome.get("model_decision_recorded")),
        "character_readback_passed": bool(character.get("native_readback_passed")),
        "release_ready": False,
        "fidelity_verified": False,
        "incomplete": incomplete,
    }
