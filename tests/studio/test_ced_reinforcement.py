"""Offline CED mapping contextual-bandit reinforcement feedback contracts."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "learning"))

import ced_reinforcement as learner


def _experience(i, *, outcome="PASS", project=None, approved=True, native=True):
    return {
        "kind": "cutsceneai.ced.mapping_experience",
        "schema_version": "1",
        "case_sha256": hashlib.sha256(f"case{i}".encode()).hexdigest(),
        "project_group_sha256": hashlib.sha256(
            f"project{project if project is not None else i}".encode()).hexdigest(),
        "ced": "camera.fov",
        "rule_id": "camera-lens-conversion",
        "source_engine": "unity", "target_engine": "unreal",
        "source_version": "6000.3", "target_version": "5.8",
        "test_outcome": outcome,
        "native_readback_verified": native,
        "human_reviewed": approved,
        "evidence_sha256": hashlib.sha256(f"evidence{i}".encode()).hexdigest(),
    }


def test_rl_scores_distinct_training_projects_and_heldout_success_without_promoting():
    rows = [_experience(i, project=i) for i in range(4)]
    result = learner.train_offline(rows)
    action = result["actions"][0]
    assert result["algorithm"] == "CONTEXTUAL_BANDIT_TD0_PESSIMISTIC_PRIOR"
    assert action["train_cases"] == 3
    assert action["train_project_groups"] == 3
    assert action["heldout_cases"] == 1
    assert action["heldout_mean_reward"] == 1.0
    assert action["q_value"] > 0
    assert action["policy"] == "RECOMMEND_FOR_HUMAN_REVIEW"
    assert result["can_promote_ced_rules"] is False
    assert result["can_authorize_native_transfer"] is False
    assert result["native_engine_training_executed"] is False


def test_rl_learns_negative_feedback_and_refuses_weak_policy():
    rows = [_experience(0, outcome="FAIL"), _experience(1, outcome="FAIL"),
            _experience(2, outcome="PASS"), _experience(3, outcome="FAIL")]
    result = learner.train_offline(rows)
    action = result["actions"][0]
    assert action["q_value"] < 0
    assert action["policy"] == "INSUFFICIENT_VALIDATION_NO_PROMOTION"


def test_unverified_positive_user_feedback_cannot_train_model():
    row = _experience(1, native=False)
    with pytest.raises(learner.CEDLearningError, match="readback"):
        learner.train_offline([row])
    row = _experience(1, approved=False)
    with pytest.raises(learner.CEDLearningError, match="readback"):
        learner.train_offline([row])


def test_one_project_cannot_train_and_validate_its_own_policy():
    result = learner.train_offline([_experience(i, project=1) for i in range(6)])
    row = result["actions"][0]
    assert row["train_cases"] == 0
    assert row["heldout_cases"] == 6
    assert row["policy"] == "INSUFFICIENT_VALIDATION_NO_PROMOTION"


def test_feedback_replay_is_detected():
    row = _experience(5)
    with pytest.raises(learner.CEDLearningError, match="Duplicated"):
        learner.train_offline([row, copy.deepcopy(row)])
    altered = copy.deepcopy(row)
    altered["evidence_sha256"] = "b" * 64
    with pytest.raises(learner.CEDLearningError, match="repeated"):
        learner.train_offline([row, altered])


def test_offline_export_does_not_replace_any_existing_policy(tmp_path):
    rows = [_experience(i) for i in range(4)]
    source = tmp_path / "feedback.jsonl"
    source.write_text("".join(json.dumps(row) + "\n" for row in rows))
    output = tmp_path / "learned-policy.json"
    result = learner.export_policy(source, output)
    assert result["experiences"] == 4
    assert json.loads(output.read_text()) == result
    with pytest.raises(learner.CEDLearningError, match="safe and new"):
        learner.export_policy(source, output)


def test_rl_keeps_engine_versions_separate_and_never_extrapolates():
    rows = [_experience(i) for i in range(4)]
    rows[-1]["target_version"] = "5.9"
    result = learner.train_offline(rows)
    assert len(result["actions"]) == 2
    assert all(x["policy"] == "INSUFFICIENT_VALIDATION_NO_PROMOTION"
               for x in result["actions"])


def _native_trial(tmp_path, *, status="NO_FLAGGED_DIFFERENCES", separate=True):
    comparison_file = tmp_path / "native-comparison.json"
    sampling_file = tmp_path / "sampling-plan.json"
    plan = {"source": {"project_fingerprint": "unity-sample",
                       "csir_sha256": "a" * 64}}
    comparison = {
        "kind": "cinetwin.behavior_comparison",
        "source_capture_sha256": "b" * 64,
        "target_observation_sha256": "c" * 64,
        "generation_editor_pid": 100, "observation_editor_pid": 200 if separate else 100,
        "native_persistence_status": "STRUCTURAL_READBACK_PASS_DIFFERENT_EDITOR_PROCESS",
        "acceptance_status": "STRUCTURE_AND_MEASURED_MOTION_WITHIN_TOLERANCE",
        "evaluation": {"status": status, "overall_cutscene_fidelity": "NOT_ESTABLISHED"},
    }
    sampling_file.write_text(json.dumps(plan))
    comparison_file.write_text(json.dumps(comparison))
    return comparison_file, sampling_file


def _record(tmp_path, *, reviewed=True, status="NO_FLAGGED_DIFFERENCES",
            separate=True):
    comparison, sampling = _native_trial(tmp_path, status=status, separate=separate)
    return learner.record_native_experience(
        comparison, sampling, tmp_path / "feedback.jsonl",
        ced="camera.fov", rule_id="camera-lens-conversion",
        source_version="6000.3", target_version="5.8", human_reviewed=reviewed)


def test_native_feedback_collector_rewards_only_reviewed_distinct_process_success(tmp_path):
    row = _record(tmp_path)
    assert row["test_outcome"] == "PASS"
    assert row["native_readback_verified"] is True
    assert len((tmp_path / "feedback.jsonl").read_text().splitlines()) == 1
    assert _record(tmp_path) == row
    assert len((tmp_path / "feedback.jsonl").read_text().splitlines()) == 1


def test_unreviewed_native_observation_stays_incomplete_feedback(tmp_path):
    row = _record(tmp_path, reviewed=False)
    assert row["test_outcome"] == "INCOMPLETE"
    assert row["native_readback_verified"] is True
    assert row["human_reviewed"] is False


def test_same_editor_pid_cannot_gain_positive_rl_reward(tmp_path):
    row = _record(tmp_path, separate=False)
    assert row["test_outcome"] == "INCOMPLETE"
    assert row["native_readback_verified"] is False


def test_failed_native_comparison_yields_negative_reward(tmp_path):
    row = _record(tmp_path, reviewed=True, status="DIFFERENCES_DETECTED")
    assert row["test_outcome"] == "FAIL"
    assert row["native_readback_verified"] is False


def test_native_reward_conflicting_replay_is_rejected(tmp_path):
    _record(tmp_path, reviewed=False)
    with pytest.raises(learner.CEDLearningError, match="conflicting"):
        _record(tmp_path, reviewed=True)
