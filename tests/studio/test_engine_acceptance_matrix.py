"""Native acceptance matrix remains evidence-only, never a synthetic pass certificate."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "studio"))

import engine_acceptance_matrix as matrix


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _case(workspace, scenario, index):
    folder = workspace / "candidates" / ("c" + str(index)) / ("native-acceptance-" + str(index))
    source = {
        "project_fingerprint": "unity-held-out" if scenario == "HELD_OUT_SOURCE_PROJECT" else "unity-dev",
        "csir_sha256": "a" * 64, "sequence_ref": "Assets/Scene.playable|guid=a|local=1",
    }
    native = {
        "kind": "cinetwin.target_behavior_observation", "source": source,
        "target": {
            "engine": "unreal", "engine_version": "5.8.1", "editor_pid": 200,
            "project_identity_sha256": "b" * 64,
        },
        "coverage": {"sample_count": 2, "full_sample_count": 2,
                     "full_temporal_coverage": True},
        "samples": [{"time_seconds": 0}, {"time_seconds": 1}],
    }
    target_sha = _write(folder / "target-behavior.json", native)
    plan_sha = _write(folder / "sampling-plan.json", {"source": source})
    persistence_sha = _write(folder / "persistence.json", {"status": "NATIVE_EDITOR_OBSERVED"})
    comparison = {
        "kind": "cinetwin.behavior_comparison", "acceptance_status":
        "STRUCTURE_AND_MEASURED_MOTION_WITHIN_TOLERANCE",
        "native_persistence_status": "STRUCTURAL_READBACK_PASS_DIFFERENT_EDITOR_PROCESS",
        "generation_editor_pid": 100, "observation_editor_pid": 200,
        "target_observation_sha256": target_sha,
        "sampling_plan_sha256": plan_sha,
        "persistence_sha256": persistence_sha,
        "source_capture_sha256": "c" * 64,
        "evaluation": {"status": "NO_FLAGGED_DIFFERENCES",
                       "overall_cutscene_fidelity": "NOT_ESTABLISHED"},
        "rig_motion_diagnostics": [{
            "joint_reference_orientation": {"status": "PASS"},
            "anatomical_mesh_forward": {"status": "PASS"},
        }],
        "entities": [{"source_max_motion_from_start_cm": 25.0}],
        "character_conversion": {
            "source_entity_id": "char",
            "reopened_character_readback_status": "PASS",
        },
    }
    if scenario == "TIMELINE_ACTOR_BLEND":
        _write(folder.parent / "transfer-plan.json", {
            "actions": [{"source_behavior_strategy":
                         "verified_unity_blend_evaluated_actor_world"}]})
        _write(folder.parent / "coverage-report.json", {
            "timeline_blend_analysis": {"source_feature_count": 1}})
    comparison_sha = _write(folder / "comparison.json", comparison)
    return {
        "scenario": scenario,
        "evidence_path": str((folder / "comparison.json").relative_to(workspace)),
        "evidence_sha256": comparison_sha,
    }


def _manifest(tmp_path):
    return {"kind": matrix.KIND, "schema_version": "1",
            "cases": [_case(tmp_path, scenario, i)
                      for i, scenario in enumerate(matrix.REQUIRED)]}


def test_complete_synthetic_evidence_is_review_only_not_live_engine_certificate(tmp_path):
    manifest = _manifest(tmp_path)
    result = matrix.evaluate(manifest, tmp_path)
    assert len(result["scenarios"]) == len(matrix.REQUIRED)
    assert result["status"] == "EVIDENCE_COMPLETE_REQUIRES_HUMAN_ENGINE_REVIEW"
    assert result["acceptance_complete"] is False
    assert result["native_engine_fidelity_proven"] is False


def test_missing_native_scenario_cannot_be_called_complete(tmp_path):
    manifest = _manifest(tmp_path)
    manifest["cases"].pop()
    with pytest.raises(matrix.MatrixError, match="Incomplete|scenario"):
        matrix.evaluate(manifest, tmp_path)


def test_changed_native_observation_is_detected_by_independent_sha(tmp_path):
    manifest = _manifest(tmp_path)
    row = manifest["cases"][0]
    path = tmp_path / row["evidence_path"]
    _write(path.parent / "target-behavior.json", {"modified": True})
    with pytest.raises(matrix.MatrixError, match="altered evidence"):
        matrix.evaluate(manifest, tmp_path)


def test_held_out_project_must_not_be_same_development_source(tmp_path):
    manifest = _manifest(tmp_path)
    held = next(row for row in manifest["cases"]
                if row["scenario"] == "HELD_OUT_SOURCE_PROJECT")
    comparison_path = tmp_path / held["evidence_path"]
    folder = comparison_path.parent
    target = json.loads((folder / "target-behavior.json").read_text())
    target["source"]["project_fingerprint"] = "unity-dev"
    observed_sha = _write(folder / "target-behavior.json", target)
    plan = json.loads((folder / "sampling-plan.json").read_text())
    plan["source"]["project_fingerprint"] = "unity-dev"
    plan_sha = _write(folder / "sampling-plan.json", plan)
    comparison = json.loads(comparison_path.read_text())
    comparison["target_observation_sha256"] = observed_sha
    comparison["sampling_plan_sha256"] = plan_sha
    held["evidence_sha256"] = _write(comparison_path, comparison)
    with pytest.raises(matrix.MatrixError, match="Held-out project"):
        matrix.evaluate(manifest, tmp_path)


def test_same_unreal_editor_process_cannot_prove_native_persistence(tmp_path):
    manifest = _manifest(tmp_path)
    row = manifest["cases"][0]
    path = tmp_path / row["evidence_path"]
    comparison = json.loads(path.read_text())
    comparison["generation_editor_pid"] = comparison["observation_editor_pid"]
    row["evidence_sha256"] = _write(path, comparison)
    with pytest.raises(matrix.MatrixError, match="distinct Unreal Editor"):
        matrix.evaluate(manifest, tmp_path)


def test_symlinked_evidence_is_not_accepted(tmp_path):
    manifest = _manifest(tmp_path)
    row = manifest["cases"][0]
    path = tmp_path / row["evidence_path"]
    moved = path.with_name("original-comparison.json")
    path.rename(moved)
    try:
        path.symlink_to(moved)
    except (OSError, NotImplementedError):
        pytest.skip("This test environment does not support symbolic links.")
    with pytest.raises(matrix.MatrixError, match="symlinks"):
        matrix.evaluate(manifest, tmp_path)
