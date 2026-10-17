"""Behavior-comparison regressions for source/target runtime samples."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "cinetwin"))

from behavior_compare import BehavioralComparisonError, compare
from sampling_plan import build_plan


def _time(value: int) -> dict:
    return {"value": value, "rate": {"numerator": 1, "denominator": 1}}


def _fixtures() -> tuple[dict, dict, dict]:
    csir = {
        "cutscene_id": "unit-test-cinematic",
        "source": {
            "engine": "unity", "engine_version": "6000.3.8f1",
            "sequence_ref": "Assets/timeline.playable|guid=a|local=1",
            "project_fingerprint": "sha256:fixture",
        },
        "timing": {
            "display_rate": {"numerator": 4, "denominator": 1},
            "playback_start": _time(0),
            "playback_end": _time(1),
        },
        "entities": [
            {"entity_id": "character", "name": "Alice", "ced_type": "entity.character"},
            {"entity_id": "camera", "name": "Camera", "ced_type": "entity.camera"},
            {"entity_id": "audio", "name": "Sound", "ced_type": "entity.audio"},
        ],
        "tracks": [{
            "track_id": "animate", "ced_type": "animation.track",
            "binding_entity_id": "character",
            "sections": [{
                "section_id": "walk", "ced_type": "animation.section",
                "start": _time(0), "end": _time(1), "payload": {},
            }],
        }],
    }
    plan = build_plan(csir, csir_sha256="ab" * 32)

    def transform(x: float) -> dict:
        return {
            "position_m": [x, 0, 0],
            "rotation_xyzw": [0, 0, 0, 1],
            "scale_xyz": [1, 1, 1],
        }

    source = {
        "kind": "cinetwin.behavior_capture",
        "cutscene_id": plan["cutscene_id"],
        "source": dict(plan["source"]),
        "capture_layers": [
            {"layer": item["layer"], "status": (
                "CAPTURED" if item["status"] == "PLANNED" else "NOT_IMPLEMENTED"
            )} for item in plan["capabilities"]
        ],
        "errors": [],
        "rigs": [{
            "entity_id": "character",
            "rig_type": "skinned_mesh_bones",
            "bones": [{
                "bone_id": "hips", "parent_bone_id": "",
                "hierarchy_path": "Alice/Hips",
            }],
        }],
        "samples": [],
    }
    target = {
        "kind": "cinetwin.target_behavior_observation",
        "cutscene_id": plan["cutscene_id"],
        "source": dict(plan["source"]),
        "coverage": {
            "full_temporal_coverage": True,
            "sample_count": len(plan["samples"]),
            "unmapped_source_entities": [{
                "entity_id": "audio", "source_name": "Sound",
            }],
        },
        "native_rigs": [{
            "entity_id": "character",
            "native_target_bones": [{
                "bone_name": "pelvis", "parent_bone_name": None,
            }],
        }],
        "samples": [],
    }
    for index, moment in enumerate(plan["samples"]):
        x = index / (len(plan["samples"]) - 1)
        source["samples"].append({
            "time_seconds": moment["time_seconds"],
            "entities": [
                {"entity_id": "character", "world_transform": transform(x)},
                {"entity_id": "camera", "world_transform": transform(0),
                 "camera": {"vertical_fov_degrees": 40}},
                {"entity_id": "audio", "world_transform": transform(0)},
            ],
            "skeletal_poses": [{
                "entity_id": "character", "bones": [{
                    "bone_id": "hips",
                    "local_transform": transform(x),
                    "world_transform": transform(x),
                }],
            }],
        })
        target["samples"].append({
            "time_seconds": moment["time_seconds"],
            "entities": [
                {"entity_id": "character", "actor_label": "AliceUnreal",
                 "world_transform": transform(x)},
                {"entity_id": "camera", "actor_label": "CameraUnreal",
                 "world_transform": transform(0)},
            ],
            "skeletal_poses": [{
                "entity_id": "character", "bones": [{
                    "bone_name": "pelvis", "world_position_m": [x, 0, 0],
                    "unreal_world_rotation_xyzw": [0, 0, 0, 1],
                    "unreal_world_scale_xyz": [1, 1, 1],
                }],
            }],
        })
    return plan, source, target


def test_matched_canonical_actor_observations_are_zero_error() -> None:
    plan, source, target = _fixtures()
    result = compare(plan, source, target)
    assert result["evaluation"]["status"] == "NO_FLAGGED_DIFFERENCES"
    assert result["evaluation"]["overall_cutscene_fidelity"] == "NOT_ESTABLISHED"
    assert result["entities"][0]["max_world_position_error_cm"] == 0
    assert result["evaluation"]["sampling_times"] == 5
    assert result["evaluation"]["unmapped_entity_count"] == 1
    assert result["rig_motion_diagnostics"][0]["source"]["bone_count"] == 1


def test_world_position_and_relative_trajectory_differences_are_measured() -> None:
    plan, source, target = _fixtures()
    for frame in target["samples"]:
        frame["entities"][0]["world_transform"]["position_m"][0] += 0.07
    result = compare(plan, source, target)
    alice = next(e for e in result["entities"] if e["source_name"] == "Alice")
    assert alice["max_world_position_error_cm"] == pytest.approx(7.0)
    assert alice["max_relative_trajectory_error_cm"] == 0
    assert "WORLD_POSITION_OUTSIDE_TOLERANCE" in alice["flags"]
    assert result["evaluation"]["status"] == "DIFFERENCES_DETECTED"


def test_static_target_actor_is_flagged_separately_from_native_bone_motion() -> None:
    plan, source, target = _fixtures()
    for frame in target["samples"]:
        frame["entities"][0]["world_transform"]["position_m"] = [0, 0, 0]
    result = compare(plan, source, target)
    alice = next(e for e in result["entities"] if e["source_name"] == "Alice")
    assert "SOURCE_MOVES_BUT_TARGET_ACTOR_STATIC" in alice["flags"]
    assert result["rig_motion_diagnostics"][0]["flags"] == []


def test_source_bones_move_but_unreal_native_bones_are_static() -> None:
    plan, source, target = _fixtures()
    for frame in target["samples"]:
        frame["skeletal_poses"][0]["bones"][0]["world_position_m"] = [0, 0, 0]
    report = compare(plan, source, target)
    assert "SOURCE_BONES_MOVE_BUT_TARGET_BONES_STATIC" in (
        report["rig_motion_diagnostics"][0]["flags"]
    )


def test_quaternion_sign_does_not_create_false_rotation_error() -> None:
    plan, source, target = _fixtures()
    for frame in target["samples"]:
        frame["entities"][0]["world_transform"]["rotation_xyzw"] = [0, 0, 0, -1]
    report = compare(plan, source, target)
    alice = next(e for e in report["entities"] if e["source_name"] == "Alice")
    assert alice["max_world_rotation_error_degrees"] == pytest.approx(0)


def test_detect_rotational_mismatch() -> None:
    plan, source, target = _fixtures()
    for frame in target["samples"]:
        frame["entities"][0]["world_transform"]["rotation_xyzw"] = [0, 0, 1, 0]
    report = compare(plan, source, target)
    alice = next(e for e in report["entities"] if e["source_name"] == "Alice")
    assert alice["max_world_rotation_error_degrees"] == pytest.approx(180)
    assert "WORLD_ROTATION_OUTSIDE_TOLERANCE" in alice["flags"]


def test_partial_smoke_capture_is_rejected_before_comparison() -> None:
    plan, source, target = _fixtures()
    target["samples"] = target["samples"][:-1]
    with pytest.raises(BehavioralComparisonError, match="full comparable target"):
        compare(plan, source, target)


def test_incorrect_source_identity_is_rejected() -> None:
    plan, source, target = _fixtures()
    target["source"]["csir_sha256"] = "different"
    with pytest.raises(BehavioralComparisonError, match="source identity"):
        compare(plan, source, target)


def test_missing_sample_or_target_binding_is_not_silently_ignored() -> None:
    plan, source, target = _fixtures()
    target["samples"][2]["entities"].pop()
    with pytest.raises(BehavioralComparisonError, match="actor identities"):
        compare(plan, source, target)


def test_unmapped_source_semantics_are_never_called_equivalent() -> None:
    plan, source, target = _fixtures()
    target["coverage"]["unmapped_source_entities"] = []
    with pytest.raises(BehavioralComparisonError, match="do not cover"):
        compare(plan, source, target)


def test_source_capture_still_requires_complete_rig_observations() -> None:
    plan, source, target = _fixtures()
    source["samples"][2]["skeletal_poses"][0]["bones"] = []
    with pytest.raises(BehavioralComparisonError, match="failed verification"):
        compare(plan, source, target)


def test_inputs_are_not_modified_by_comparison() -> None:
    plan, source, target = _fixtures()
    before = copy.deepcopy((plan, source, target))
    compare(plan, source, target)
    assert (plan, source, target) == before
