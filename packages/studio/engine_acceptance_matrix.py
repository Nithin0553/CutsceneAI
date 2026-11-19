"""Read-only evidence matrix for final cross-engine acceptance on a workstation.

The matrix does not run Unity/Unreal or certify that JSON was truly generated
by an Editor; it independently checks completeness, SHA256 linkage, scenario
coverage, native save/reopen process IDs and previously measured diagnostics.
Actual editor logs, frame renders and a reviewer remain mandatory.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

KIND = "cutsceneai.studio.engine_acceptance_matrix"
REQUIRED = (
    "STATIC_MESH_FACING",
    "MOVING_CHARACTER_TURN",
    "TIMELINE_ACTOR_BLEND",
    "CALIBRATED_JOINT_AXES",
    "NATIVE_SAVE_REOPEN",
    "HELD_OUT_SOURCE_PROJECT",
)
_SHA = re.compile(r"^[0-9a-f]{64}$")


class MatrixError(ValueError):
    pass


def _json_bound(path: Path, root: Path) -> dict:
    # Inspect links *before* resolution; checking is_symlink after resolve
    # silently loses the evidence that a file was redirected elsewhere.
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise MatrixError("Acceptance evidence cannot pass through symlinks.")
    path = path.resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise MatrixError("Acceptance evidence must be a regular file inside the selected workspace.")
    if path.stat().st_size > 64 * 1024 * 1024:
        raise MatrixError("Acceptance evidence exceeds the bounded file limit.")
    try:
        document = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, UnicodeError) as error:
        raise MatrixError("Acceptance evidence could not be decoded.") from error
    if not isinstance(document, dict):
        raise MatrixError("Acceptance evidence must be a JSON object.")
    return document


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_hash(document: dict, key: str):
    if not isinstance(document.get(key), str) or not _SHA.fullmatch(document[key]):
        raise MatrixError("Native evidence lacks a complete SHA256: " + key)


def evaluate(matrix: dict[str, Any], workspace: str | Path) -> dict[str, Any]:
    """Review saved native acceptance evidence; never issue an engine-fidelity certificate."""
    root = Path(workspace).resolve()
    if (matrix.get("kind") != KIND or matrix.get("schema_version") != "1"
            or not isinstance(matrix.get("cases"), list)
            or len(matrix["cases"]) != len(REQUIRED)):
        raise MatrixError("Incomplete or unversioned engine acceptance matrix.")
    cases = matrix["cases"]
    scenarios = [row.get("scenario") for row in cases if isinstance(row, dict)]
    if len(scenarios) != len(REQUIRED) or set(scenarios) != set(REQUIRED):
        raise MatrixError("Every native acceptance scenario must appear exactly once.")

    details: list[dict[str, Any]] = []
    identities = {}
    for item in sorted(cases, key=lambda row: str(row["scenario"])):
        scenario = item["scenario"]
        relative = item.get("evidence_path")
        expected = item.get("evidence_sha256")
        if (not isinstance(relative, str) or not relative
                or Path(relative).is_absolute() or ".." in Path(relative).parts
                or not isinstance(expected, str) or not _SHA.fullmatch(expected)):
            raise MatrixError("Scenario evidence path and SHA256 must be explicit and safe.")
        evidence = root / relative
        comparison = _json_bound(evidence, root)
        if _sha(evidence) != expected:
            raise MatrixError("The native acceptance comparison changed after matrix preparation.")
        folder = evidence.parent
        if evidence.name != "comparison.json" or not folder.name.startswith("native-acceptance-"):
            raise MatrixError("Expected untouched Studio reopened native-acceptance output.")
        native = _json_bound(folder / "target-behavior.json", root)
        plan = _json_bound(folder / "sampling-plan.json", root)
        persistence = _json_bound(folder / "persistence.json", root)
        for name, artifact in (
            ("target_observation_sha256", folder / "target-behavior.json"),
            ("sampling_plan_sha256", folder / "sampling-plan.json"),
            ("persistence_sha256", folder / "persistence.json"),
        ):
            _require_hash(comparison, name)
            if comparison[name] != _sha(artifact):
                raise MatrixError("Native acceptance references altered evidence: " + name)
        _require_hash(comparison, "source_capture_sha256")
        source_id = plan.get("source", {})
        observed_source_id = native.get("source", {})
        if native.get("kind") != "cinetwin.target_behavior_observation":
            raise MatrixError("Missing actual target CineTwin observation.")
        if any(source_id.get(k) != observed_source_id.get(k) or not source_id.get(k)
               for k in ("project_fingerprint", "csir_sha256", "sequence_ref")):
            raise MatrixError("Native observation does not belong to the exact Unity source.")
        project = native.get("target", {})
        if (project.get("engine") != "unreal"
                or not str(project.get("engine_version", "")).startswith("5.8.")
                or not _SHA.fullmatch(str(project.get("project_identity_sha256", "")))):
            raise MatrixError("Target engine/version/project identity not measured by Unreal.")
        pid_a, pid_b = comparison.get("generation_editor_pid"), comparison.get("observation_editor_pid")
        if (type(pid_a) is not int or type(pid_b) is not int
                or pid_a <= 0 or pid_b <= 0 or pid_a == pid_b
                or project.get("editor_pid") != pid_b):
            raise MatrixError("Native persistence was not observed in a distinct Unreal Editor process.")
        coverage = native.get("coverage", {})
        if (coverage.get("full_temporal_coverage") is not True
                or coverage.get("sample_count") != coverage.get("full_sample_count")
                or not native.get("samples") or
                len(native["samples"]) != coverage.get("sample_count")):
            raise MatrixError("Native observation does not cover the full source grid.")
        # An all-true coverage flag and matching counts do not prove that
        # native observations were sampled on the exact Unity time grid.
        # Require every planned frame, in order, including the final frame.
        planned_samples = plan.get("samples")
        observed_samples = native.get("samples")
        if (not isinstance(planned_samples, list) or len(planned_samples) < 2
                or len(planned_samples) != len(observed_samples)):
            raise MatrixError("Native acceptance lacks the complete Unity sampling time grid.")
        previous_time = None
        for index, (planned_row, observed_row) in enumerate(
                zip(planned_samples, observed_samples)):
            if not isinstance(planned_row, dict) or not isinstance(observed_row, dict):
                raise MatrixError("Invalid source/target acceptance sample at frame "
                                  + str(index))
            try:
                source_time = float(planned_row["time_seconds"])
                target_time = float(observed_row["time_seconds"])
            except (KeyError, ValueError, TypeError) as error:
                raise MatrixError("Acceptance sample time is missing or malformed.") from error
            if (not math.isfinite(source_time) or not math.isfinite(target_time)
                    or abs(source_time - target_time) > 1e-6
                    or (previous_time is not None and source_time <= previous_time)):
                raise MatrixError(
                    "Reopened Unreal time samples differ from the exact Unity source grid."
                )
            previous_time = source_time

        if (comparison.get("kind") != "cinetwin.behavior_comparison"
                or comparison.get("acceptance_status") != "STRUCTURE_AND_MEASURED_MOTION_WITHIN_TOLERANCE"
                or comparison.get("evaluation", {}).get("status") != "NO_FLAGGED_DIFFERENCES"
                or comparison.get("evaluation", {}).get("overall_cutscene_fidelity") != "NOT_ESTABLISHED"
                or comparison.get("native_persistence_status")
                != "STRUCTURAL_READBACK_PASS_DIFFERENT_EDITOR_PROCESS"):
            raise MatrixError("Native evidence is partial, mismatched or falsely claims overall fidelity.")

        metrics = comparison.get("rig_motion_diagnostics", [])
        if scenario == "STATIC_MESH_FACING" and not any(
                row.get("anatomical_mesh_forward", {}).get("status") == "PASS"
                for row in metrics):
            raise MatrixError("Static facing requires independently approved anatomical mesh axis parity.")
        if scenario == "CALIBRATED_JOINT_AXES" and not any(
                row.get("joint_reference_orientation", {}).get("status") == "PASS"
                for row in metrics):
            raise MatrixError("Rig axes require native paired reference pose measurements.")
        if scenario == "MOVING_CHARACTER_TURN":
            if not any(float(row.get("source_max_motion_from_start_cm", 0)) > 1
                       for row in comparison.get("entities", [])):
                raise MatrixError("Moving character trial has no observed moving source actor.")
            proof = comparison.get("character_conversion") or {}
            if (not proof.get("source_entity_id")
                    or proof.get("reopened_character_readback_status") != "PASS"):
                raise MatrixError("Moving character native retargeted motion lacks reopened readback.")
        if scenario == "TIMELINE_ACTOR_BLEND":
            candidate = folder.parent
            transfer_plan = _json_bound(candidate / "transfer-plan.json", root)
            report = _json_bound(candidate / "coverage-report.json", root)
            strategies = {action.get("source_behavior_strategy")
                          for action in transfer_plan.get("actions", [])
                          if isinstance(action, dict)}
            if ("verified_unity_blend_evaluated_actor_world" not in strategies
                    or not report.get("timeline_blend_analysis", {}).get("source_feature_count", 0)):
                raise MatrixError("Blend trial did not bake actual evaluated Unity actor world motion.")
        identities[scenario] = {
            "source_fingerprint": source_id["project_fingerprint"],
            "target_project_identity": project["project_identity_sha256"],
        }
        details.append({
            "scenario": scenario, "status": "EVIDENCE_COMPLETE_REQUIRES_HUMAN_ENGINE_REVIEW",
            "evidence_sha256": expected, "source_project_fingerprint": source_id["project_fingerprint"],
            "target_engine_version": project["engine_version"],
        })

    first = identities["NATIVE_SAVE_REOPEN"]
    held = identities["HELD_OUT_SOURCE_PROJECT"]
    if held["source_fingerprint"] == first["source_fingerprint"]:
        raise MatrixError("Held-out project must be independent of the development source project.")
    return {
        "kind": "cutsceneai.studio.engine_acceptance_matrix_review",
        "schema_version": "1",
        "status": "EVIDENCE_COMPLETE_REQUIRES_HUMAN_ENGINE_REVIEW",
        "scenarios": details,
        "acceptance_complete": False,
        "native_engine_fidelity_proven": False,
        "remaining": [
            "Independent reviewer confirms Unity and Unreal logs/asset provenance.",
            "Compare rendered cameras, character silhouettes, material appearance and audio separately.",
            "Native control/editor behavior was not executed by this code-only review tool.",
        ],
    }
