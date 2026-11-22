"""Phase 10.2 source-bound character facing review and LangGraph routing.

All native samples and engine objects are synthetic test fixtures. No model
selection can create an actor/mesh/skeleton rotation in this implementation.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for folder in ("packages/studio", "packages/cinetwin", "packages/ced",
               "integrations/unreal", "tests/studio"):
    route = str(ROOT / folder)
    if route not in sys.path:
        sys.path.insert(0, route)

import agent_intent_router
import studio_character_facing_review as review
import studio_element7_readback as readback
from test_element7_native_readback import (
    _native_facing_owner_fixture, _put, _scenario,
)


def _workspace(tmp_path, *, attached=True):
    workspace, job, folder = _scenario(
        tmp_path, with_element3=True, complete=True,
        ai_agents_enabled=True, automatic_setup=True,
    )
    if attached:
        _native_facing_owner_fixture(folder, job)
    _put(folder / "element7-readback.json",
         readback.build(workspace, job["job_id"], folder))
    return workspace, job, folder


def test_exact_reopened_native_facing_review_is_redacted_and_nonexecuting(tmp_path):
    workspace, job, folder = _workspace(tmp_path)
    result = review.build(workspace, job)
    assert result["kind"] == review.KIND
    assert result["status"] == "REOPENED_CHARACTER_OWNER_DIAGNOSTIC_ONLY"
    assert result["observed_character_count"] == 1
    assert result["native_owner_observation_available"] is True
    assert result["static_native_owner_candidates_without_source_authority"] == 1
    assert result["native_edit_authorized"] is False
    assert result["model_command_authorized"] is False
    assert result["source_rest_pose_and_root_motion_calibrated"] is False
    assert result["full_cutscene_fidelity_verified"] is False
    serialized = json.dumps(result)
    assert "AliceUnreal" not in serialized
    assert "GuardTarget" not in serialized
    assert "/Game/" not in serialized
    assert str(folder) not in serialized

    routed = agent_intent_router.route(
        "The character is facing the wrong direction.",
        generation_complete=True,
        native_material_fallback_slots=2,
        source_albedo_provenance=True,
        completed_repairs=0,
        repair_budget=2,
        independent_issues=[],
        character_facing_review=result,
    )
    assert routed["disposition"] == "NATIVE_CHARACTER_ROTATION_OWNERSHIP_REVIEW_ONLY"
    assert routed["safe_strategies"] == ["report_only"]
    assert routed["model_can_authorize_native_commands"] is False


def test_absent_independent_native_ownership_does_not_grant_facing_strategy(tmp_path):
    workspace, job, _ = _workspace(tmp_path, attached=False)
    result = review.build(workspace, job)
    assert result["status"] == "NATIVE_CHARACTER_OWNER_NOT_OBSERVED"
    assert result["native_owner_observation_available"] is False
    routed = agent_intent_router.route(
        "The character is facing wrong.",
        generation_complete=True,
        native_material_fallback_slots=3,
        source_albedo_provenance=True,
        completed_repairs=0, repair_budget=2, independent_issues=[],
        character_facing_review=result,
    )
    assert routed["safe_strategies"] == ["report_only"]
    assert routed["disposition"] != "NATIVE_CHARACTER_ROTATION_OWNERSHIP_REVIEW_ONLY"


@pytest.mark.parametrize("message,allowed", [
    ("The character is facing the wrong direction.", True),
    ("Fix the character orientation.", True),
    ("The camera is facing the wrong direction.", False),
    ("Fix the character position.", False),
    ("Fix the character facing and animation material.", False),
    ("Fix the guard's audio.", False),
    ("Don't move the camera.", False),
    ("", False),
])
def test_facing_message_scope_is_narrow_and_not_a_write_permission(message, allowed):
    assert bool(review.relevant_feedback(message)) is allowed


@pytest.mark.parametrize("tamper", ["job", "owner_authority", "native_hash", "owner_rig"])
def test_facing_review_refuses_foreign_or_untrusted_owner_evidence(tmp_path, tamper):
    workspace, job, folder = _workspace(tmp_path)
    if tamper == "job":
        job["candidate_id"] = "foreign"
        with pytest.raises(review.CharacterFacingReviewError):
            review.build(workspace, job)
        return

    path = folder / "native-character-facing-ownership.json"
    record = json.loads(path.read_text())
    if tamper == "owner_authority":
        record["characters"][0]["native_edit_authorized"] = True
    elif tamper == "owner_rig":
        record["characters"][0]["entity_id"] = "foreign-rig"
    else:
        record["target_observation_sha256"] = "0" * 64
    _put(path, record)
    comparison_file = folder / "comparison.json"
    comparison = json.loads(comparison_file.read_text())
    comparison["native_facing_ownership_sha256"] = readback._safe_json(path)[1]
    _put(comparison_file, comparison)
    with pytest.raises(review.CharacterFacingReviewError):
        review.build(workspace, job)


def test_mixed_character_camera_feedback_or_exhausted_budget_stays_report_only(tmp_path):
    workspace, job, _ = _workspace(tmp_path)
    result = review.build(workspace, job)
    for message, completed in (
        ("Fix character facing and camera position.", 0),
        ("The character is facing wrong.", 2),
    ):
        routed = agent_intent_router.route(
            message, generation_complete=True, native_material_fallback_slots=1,
            source_albedo_provenance=True, completed_repairs=completed,
            repair_budget=2, independent_issues=[],
            character_facing_review=result,
        )
        assert routed["safe_strategies"] == ["report_only"]
        assert routed["model_can_authorize_native_commands"] is False
