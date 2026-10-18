"""Regression tests for independent source-vs-target sampled actor hierarchy parity."""
from __future__ import annotations

import copy
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "cinetwin"))
from hierarchy_verify import HierarchyVerificationError, verify_hierarchy


def _trs(x: float, y: float = 0.0, q=None, scale=None):
    return {
        "position_m": [x, y, 0.0],
        "rotation_xyzw": q or [0.0, 0.0, 0.0, 1.0],
        "scale_xyz": scale or [1.0, 1.0, 1.0],
    }


def _fixtures():
    metadata = {
        "csir_sha256": "a" * 64,
        "sequence_ref": "some-source-sequence",
        "project_fingerprint": "project",
    }
    planned_times = [0.0, 1.0, 4.0, 7.0, 8.0, 9.0]
    plan = {
        "kind": "cinetwin.sampling_plan",
        "cutscene_id": "test-cutscene",
        "source": metadata,
        "entities": [
            {"entity_id": "moving", "name": "Moving"},
            {"entity_id": "child", "name": "Child"},
        ],
        "samples": [{"time_seconds": t} for t in planned_times],
    }
    source = {
        "kind": "cinetwin.behavior_capture",
        "cutscene_id": "test-cutscene",
        "source": metadata,
        "errors": [],
        "samples": [
            {
                "time_seconds": t,
                "entities": [
                    {"entity_id": "moving", "world_transform": _trs(t / 10)},
                    {"entity_id": "child", "world_transform": _trs(t / 10 + 2)},
                ],
            } for t in planned_times
        ],
    }
    target = {
        "kind": "cinetwin.target_behavior_observation",
        "cutscene_id": "test-cutscene",
        "source": metadata,
        "coverage": {"sample_count": 5},
        "samples": [
            {
                "time_seconds": t,
                "entities": [
                    {"entity_id": "moving", "actor_label": "MOV",
                     "world_transform": _trs(t / 10)},
                    {"entity_id": "child", "actor_label": "CH",
                     "world_transform": _trs(t / 10 + 2)},
                ],
                "motion_layers": [
                    {"entity_id": "moving", "actor_label": "MOV",
                     "attached_to_actor_label": None},
                    {"entity_id": "child", "actor_label": "CH",
                     "attached_to_actor_label": "MOV"},
                ],
            } for t in planned_times[:5]
        ],
    }
    hierarchy = {
        "kind": "cinetwin.target_hierarchy_plan",
        "cutscene_id": "test-cutscene",
        "unresolved_source_parents": [],
        "planned_actor_attachments": [{
            "entity_id": "child",
            "actor_label": "CH",
            "source_parent_entity_id": "moving",
            "parent_actor_label": "MOV",
        }],
    }
    return plan, source, target, hierarchy


def test_correct_parent_and_child_world_positions_match_at_selected_times():
    plan, source, target, hierarchy = _fixtures()
    report = verify_hierarchy(plan, source, target, hierarchy)
    assert report["status"] == "MATCH_AT_SAMPLED_TIMES"
    assert report["sample_count"] == 5
    assert report["total_source_sample_count"] == 6
    edge = report["attachments"][0]
    assert edge["max_parent_relative_offset_error_cm"] == 0.0
    assert edge["max_child_world_position_error_cm"] == 0.0
    assert edge["flags"] == []


def test_keep_world_can_be_attached_correctly_with_wrong_local_offset():
    plan, source, target, hierarchy = _fixtures()
    for sample in target["samples"]:
        sample["entities"][1]["world_transform"]["position_m"][0] += 0.4
    report = verify_hierarchy(plan, source, target, hierarchy)
    edge = report["attachments"][0]
    assert report["status"] == "MISMATCH_DETECTED"
    assert edge["max_parent_relative_offset_error_cm"] == pytest.approx(40.0)
    assert edge["max_child_world_position_error_cm"] == pytest.approx(40.0)
    assert "PARENT_RELATIVE_OFFSET_MISMATCH" in edge["flags"]


def test_parent_world_offset_can_mismatch_while_local_offset_matches():
    plan, source, target, hierarchy = _fixtures()
    for sample in target["samples"]:
        for record in sample["entities"]:
            record["world_transform"]["position_m"][0] += 5.0
    report = verify_hierarchy(plan, source, target, hierarchy)
    edge = report["attachments"][0]
    assert edge["max_parent_relative_offset_error_cm"] == 0.0
    assert edge["max_child_world_position_error_cm"] == pytest.approx(500.0)
    assert "PARENT_RELATIVE_OFFSET_MISMATCH" not in edge["flags"]
    assert "CHILD_WORLD_POSITION_MISMATCH" in edge["flags"]


def test_correct_world_positions_do_not_hide_missing_attachment():
    plan, source, target, hierarchy = _fixtures()
    target["samples"][2]["motion_layers"][1]["attached_to_actor_label"] = None
    report = verify_hierarchy(plan, source, target, hierarchy)
    assert "TARGET_PARENT_ATTACHMENT_MISMATCH" in report["attachments"][0]["flags"]


def test_parent_rotation_is_respected_when_computing_local_offset():
    plan, source, target, hierarchy = _fixtures()
    q = [0, 0, math.sqrt(0.5), math.sqrt(0.5)]
    for sample in source["samples"]:
        sample["entities"][0]["world_transform"] = _trs(0, 0, q=q)
        sample["entities"][1]["world_transform"] = _trs(0, 2)
    for sample in target["samples"]:
        sample["entities"][0]["world_transform"] = _trs(0)
        sample["entities"][1]["world_transform"] = _trs(2)
    report = verify_hierarchy(plan, source, target, hierarchy)
    edge = report["attachments"][0]
    assert edge["max_parent_relative_offset_error_cm"] == pytest.approx(0, abs=1e-5)
    assert edge["max_child_world_position_error_cm"] == pytest.approx(2**0.5 * 200, abs=1e-4)


def test_scale_affects_parent_local_offset():
    plan, source, target, hierarchy = _fixtures()
    for sample in target["samples"]:
        sample["entities"][0]["world_transform"]["scale_xyz"] = [2, 1, 1]
    report = verify_hierarchy(plan, source, target, hierarchy)
    assert report["attachments"][0]["max_parent_relative_offset_error_cm"] == 100.0


def test_unknown_target_timestamps_cannot_be_silently_interpolated():
    plan, source, target, hierarchy = _fixtures()
    target["samples"][2]["time_seconds"] = 4.1
    with pytest.raises(HierarchyVerificationError, match="not in source plan"):
        verify_hierarchy(plan, source, target, hierarchy)


def test_source_identity_mismatch_is_rejected():
    plan, source, target, hierarchy = _fixtures()
    target["source"] = dict(target["source"], csir_sha256="different")
    with pytest.raises(HierarchyVerificationError, match="provenance"):
        verify_hierarchy(plan, source, target, hierarchy)


def test_missing_motion_layer_is_not_considered_verified():
    plan, source, target, hierarchy = _fixtures()
    target["samples"][2]["motion_layers"] = []
    with pytest.raises(HierarchyVerificationError, match="attachment observation"):
        verify_hierarchy(plan, source, target, hierarchy)


def test_source_and_target_evidence_are_not_mutated():
    fixture = _fixtures()
    before = copy.deepcopy(fixture)
    verify_hierarchy(*fixture)
    assert fixture == before
