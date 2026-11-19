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
