"""Phase 10.2 proof-only static yaw tests; all native evidence is synthetic."""
from __future__ import annotations

import copy
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for path in ("packages/studio", "packages/ced", "packages/cinetwin",
             "integrations/unreal", "tests/studio"):
    directory = str(ROOT / path)
    if directory not in sys.path:
        sys.path.insert(0, directory)

import agent_intent_router
import studio_static_character_yaw_evidence as evidence


def _canonical_yaw(degrees):
    a = math.radians(degrees) / 2
    return [0., -math.sin(a), 0., math.cos(a)]


def _native_yaw(degrees):
    a = math.radians(degrees) / 2
    return [0., 0., math.sin(a), math.cos(a)]


def _sample(degrees, index, *, target=False):
    transform = {
        "position_m": [0., 0., 0.], "rotation_xyzw": _canonical_yaw(degrees),
        "scale_xyz": [1., 1., 1.],
    }
    frame = {
        "time_seconds": index / 30,
        "entities": [{"entity_id": "guard", "world_transform": transform}],
        "skeletal_poses": [{
            "entity_id": "guard",
            "bones": ([{
                "bone_name": "Root",
                "world_position_m": [0., 0., 0.],
                "unreal_world_rotation_xyzw": _native_yaw(degrees),
            }] if target else [{
                "bone_id": "root",
                "world_transform": {
                    "position_m": [0., 0., 0.],
                    "rotation_xyzw": _canonical_yaw(degrees),
                },
            }]),
        }],
    }
    if target:
        frame["entities"][0]["actor_label"] = "GuardTarget"
        frame["skeletal_mesh_component_bases"] = [{
            "entity_id": "guard", "status": "OBSERVED",
            "target_mesh_asset_path": "/Game/Characters/Guard",
            "unreal_component_world_rotation_xyzw": _native_yaw(degrees),
        }]
    return frame


def fixture(monkeypatch, tmp_path):
    root = tmp_path / "runs"
    candidate_id = "20261122T200000Z_deadbeef"
    candidate = root / "candidates" / candidate_id
    folder = candidate / "native-acceptance-one"
    job = {
        "job_id": "a" * 32,
        "kind": "cutsceneai.studio.local_unreal_job",
        "candidate_id": candidate_id,
        "candidate_dir": str(candidate),
        "capture": str(tmp_path / "unity-capture.json"),
        "sequence_path": "/Game/Stage/LS",
        "expected_project": str(tmp_path / "NativeTest.uproject"),
        "expected_level": "/Game/Stage/L_Static",
        "setup_receipt_file": str(candidate / "setup-static-yaw-test.json"),
        "ai_agents_enabled": True,
        "generation_status": "GENERATED_UNVERIFIED",
        "automatic_setup": True,
    }
    csir = {
        "entities": [{
            "ced_type": "entity.character", "name": "Guard",
            "entity_id": "guard",
        }],
        "tracks": [],
    }
    mapping = {"entities": {"Guard": {"actor_label": "GuardTarget"}}}
    compiled = {"actions": []}
    source = {"samples": [_sample(90, i) for i in range(4)]}
    target = {
        "target": {
            "engine_version": "5.8",
            "project_identity_sha256": "b" * 64,
            "sequence_asset_path": "/Game/Stage/LS.LS",
        },
        "samples": [_sample(0, i, target=True) for i in range(4)],
    }
    sampling = {"source": {
        "csir_sha256": "a" * 64, "sequence_ref": "Assets/Guard.timeline",
        "project_fingerprint": "source-id",
    }}
    axes = {
        "kind": "cutsceneai.mesh_forward_approval",
        "schema_version": "1",
        "reviewed_anatomical_axes": True,
        "source_identity": sampling["source"].copy(),
        "target_identity": target["target"].copy(),
        "characters": {"guard": {
            "source_forward_actor_local_canonical_xyz": [0., 0., -1.],
            "target_forward_mesh_local_unreal_xyz": [1., 0., 0.],
            "target_mesh_asset_path": "/Game/Characters/Guard",
        }},
    }
    forward = {
        "status": "FAIL",
        "constant_yaw_diagnostic_status": "STABLE_SAMPLED_YAW_DIAGNOSTIC_ONLY",
        "suggested_target_actor_yaw_correction_degrees": 90.0,
        "max_sampled_yaw_variation_degrees": 0,
        "max_yaw_only_residual_degrees": 0,
        "sample_count": 4,
        "suggestion_applied": False,
        "native_actor_yaw_repair_authorized": False,
        "requires_original_full_grid_validation": True,
    }
    comparison = {
        "native_facing_ownership_sha256": "c" * 64,
        "mesh_forward_approval_sha256": "d" * 64,
        "rig_calibration_sha256": "e" * 64,
        "rig_motion_diagnostics": [{
            "entity_id": "guard",
            "flags": ["CHARACTER_MESH_ANATOMICAL_FORWARD_MISMATCH"],
            "joint_reference_orientation": {"status": "PASS"},
            "joint_angular_motion": {"status": "PASS"},
            "joint_positions": {"status": "PASS"},
            "anatomical_mesh_forward": forward,
        }],
        "entities": [{
            "entity_id": "guard",
            "flags": ["WORLD_ROTATION_OUTSIDE_TOLERANCE"],
        }],
    }
    owner = {
        "native_edit_authorized": False,
        "characters": [{
            "entity_id": "guard", "status":
            "STATIC_NATIVE_OWNER_CANDIDATE_REQUIRES_SOURCE_PROOF",
            "blocking_reasons": [], "native_edit_authorized": False,
            "target_actor_label": "GuardTarget",
            "native_skeletal_mesh_asset_path": "/Game/Characters/Guard",
            "native_actor_roll_pitch_yaw_degrees": [0., 0., 0.],
        }],
    }
    native = {
        "native_attempt": {"native_builder_completed": True},
        "distinct_reopened_editor_observed": True,
        "target_tick_sampling_status": "TICK_SYNCHRONIZED_FULL_GRID_CLAIMED",
        "readback_sha256": "f" * 64,
    }
    bounded = {
        "status": "INVESTIGATE_APPROVED_NARROW_ADAPTER_OR_REPORT_LIMITATION",
        "element3_workflow_sha256": "7" * 64,
        "repair_plan_sha256": "8" * 64,
    }
    documents = {
        "source-scratch": csir,
        "comparison.json": comparison,
        "unity-capture.json": source,
        "target-behavior.json": target,
        "mesh-forward-approval.json": axes,
        "rig-calibration.json": {"kind": "approved-fixture"},
        "native-character-facing-ownership.json": owner,
        "sampling-plan.json": sampling,
    }
    canonical = copy.deepcopy(job)
    monkeypatch.setattr(evidence.outcome, "_context", lambda *_: (
        root, candidate, canonical, csir, mapping, compiled,
    ))
    monkeypatch.setattr(evidence.outcome, "discover", lambda *_: [folder])
    monkeypatch.setattr(evidence.repair, "build", lambda *_: bounded)
    monkeypatch.setattr(evidence.readback, "build", lambda *_: native)
    monkeypatch.setattr(evidence.readback, "_safe_json", lambda path: (
        documents[Path(path).name], "9" * 64,
    ))
    return root, job, documents, owner, comparison, bounded, native


def test_static_yaw_uses_approved_source_anatomy_and_reopened_owner(monkeypatch, tmp_path):
    root, job, *_ = fixture(monkeypatch, tmp_path)
    proof = evidence.build(root, job)
    assert proof["kind"] == evidence.KIND
    assert proof["eligible"] is True
    assert proof["native_yaw_before_degrees"] == 0
    assert proof["derived_yaw_correction_degrees"] == pytest.approx(90)
    assert proof["native_yaw_after_degrees"] == pytest.approx(90)
    assert proof["sample_count"] == 4
    assert proof["native_edit_authorized"] is False
    assert proof["full_cutscene_fidelity_verified"] is False
    assert proof["character_yaw_repair_sha256"] == evidence.repair._hash({
        key: value for key, value in proof.items()
        if key != "character_yaw_repair_sha256"
    })
    assert not any("model" in name for name in proof)

    routed = agent_intent_router.route(
        "Please fix the character facing direction.",
        generation_complete=True,
        native_material_fallback_slots=0,
        source_albedo_provenance=False,
        completed_repairs=0,
        repair_budget=2,
        independent_issues=[],
        static_character_yaw_evidence=proof,
    )
    assert routed["disposition"] == "GUARDED_STATIC_CHARACTER_ACTOR_YAW_AVAILABLE"
    assert routed["safe_strategies"] == [
        "report_only", "restore_static_character_actor_yaw",
    ]
    assert routed["model_can_authorize_native_commands"] is False


@pytest.mark.parametrize("mutation,description", [
    (lambda j, d, o, c, b, n: j.update(job_id="f" * 32), "Stale job"),
    (lambda j, d, o, c, b, n: d["mesh-forward-approval.json"].update(
        reviewed_anatomical_axes=False), "approval"),
    (lambda j, d, o, c, b, n: c.pop("mesh_forward_approval_sha256"), "proof"),
    (lambda j, d, o, c, b, n: o["characters"][0].update(
        status="BLOCKED_UNVERIFIED_OWNER"), "owner"),
    (lambda j, d, o, c, b, n: c["rig_motion_diagnostics"][0][
        "anatomical_mesh_forward"].update(
            constant_yaw_diagnostic_status="UNSAFE_NONPLANAR_OR_VERTICAL_FORWARD"),
     "yaw"),
    (lambda j, d, o, c, b, n: c["rig_motion_diagnostics"][0][
        "joint_reference_orientation"].update(status="INCOMPLETE"),
     "discrepancy"),
    (lambda j, d, o, c, b, n: c["rig_motion_diagnostics"][0][
        "joint_positions"].update(status="FAIL"),
     "discrepancy"),
    (lambda j, d, o, c, b, n: c["entities"][0].update(
        flags=["WORLD_POSITION_OUTSIDE_TOLERANCE"]),
     "discrepancy"),
    (lambda j, d, o, c, b, n: b.update(
        status="STOP_MEASURED_REGRESSION_OR_NO_PROGRESS"), "proof"),
    (lambda j, d, o, c, b, n: n.update(
        distinct_reopened_editor_observed=False), "proof"),
    (lambda j, d, o, c, b, n: d["target-behavior.json"]["samples"][1][
        "entities"][0]["world_transform"]["position_m"].__setitem__(0, 0.1),
     "placement"),
    (lambda j, d, o, c, b, n: d["source-scratch"]["tracks"].append({
        "ced_type": "animation.track", "binding_entity_id": "guard",
    }), "animation"),
])
def test_static_yaw_evidence_refuses_unproven_or_moving_rig(
        monkeypatch, tmp_path, mutation, description):
    root, job, docs, owner, comparison, bounded, native = fixture(
        monkeypatch, tmp_path,
    )
    # These fake inputs exercise evidence policy only, not engine authenticity.
    mutation(job, docs, owner, comparison, bounded, native)
    with pytest.raises((evidence.StaticCharacterYawError, KeyError,
                        evidence.MeshForwardError), match=description):
        evidence.build(root, job)


def test_moving_source_or_target_bones_refuses_actor_yaw(monkeypatch, tmp_path):
    root, job, docs, *_ = fixture(monkeypatch, tmp_path)
    assert docs["source-scratch"]["tracks"] == []
    target = docs["target-behavior.json"]
    target["samples"][2]["skeletal_poses"][0]["bones"][0][
        "world_position_m"
    ][0] = 0.06
    with pytest.raises(evidence.StaticCharacterYawError, match="Moving or rotating skeletal"):
        evidence.build(root, job)


@pytest.mark.parametrize("comment,allowed", [
    ("Please fix the character facing direction.", True),
    ("Correct the guard orientation.", True),
    ("Please rotate the character.", False),
    ("Fix character position.", False),
    ("Don't fix the character facing.", False),
    ("Fix the character's facing while moving.", False),
    ("Please correct the character's animation facing.", False),
    ("Fix the camera facing.", False),
    ("Fix both characters facing.", False),
])
def test_character_facing_consent_does_not_expand_scope(comment, allowed):
    assert evidence.message_requests_static_yaw(comment) is allowed


def test_model_cannot_use_unrelated_character_report_as_yaw_evidence():
    forged = {
        "kind": "cutsceneai.studio.character_facing_owner_review",
        "eligible": True,
        "native_edit_authorized": False,
        "character_yaw_repair_sha256": "a" * 64,
    }
    route = agent_intent_router.route(
        "Please fix the character facing direction.",
        generation_complete=True,
        native_material_fallback_slots=0,
        source_albedo_provenance=False,
        completed_repairs=0,
        repair_budget=2,
        independent_issues=[],
        static_character_yaw_evidence=forged,
    )
    assert route["safe_strategies"] == ["report_only"]
