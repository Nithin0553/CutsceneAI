"""Exact two-shot shared switch proof: synthetic, not real editor fidelity."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for folder in ("packages/studio", "packages/cinetwin", "integrations/unreal",
               "tests/studio"):
    route = str(ROOT / folder)
    if route not in sys.path:
        sys.path.insert(0, route)

import agent_intent_router as router
import studio_two_shot_cut_evidence as proof


def scenario(monkeypatch, tmp_path):
    candidate = tmp_path / "runs" / "candidates" / "20261122T213000Z_deadbeef"
    folder = candidate / "native-acceptance-synthetic"
    job = {
        "kind": "cutsceneai.studio.local_unreal_job",
        "job_id": "a" * 32,
        "candidate_id": candidate.name,
        "candidate_dir": str(candidate),
        "sequence_path": "/Game/Stage/LS_Switch",
        "expected_project": str(tmp_path / "Fake.uproject"),
        "expected_level": "/Game/Stage/L_Switch",
        "ai_agents_enabled": True, "automatic_setup": True,
        "generation_status": "GENERATED_UNVERIFIED",
    }
    csir = {
        "entities": [
            {"entity_id": "camera-1", "name": "CamLeft", "ced_type": "entity.camera"},
            {"entity_id": "camera-2", "name": "CamRight", "ced_type": "entity.camera"},
        ],
        "tracks": [
            {"track_id": "shot-track-1", "ced_type": "camera.cut",
             "binding_entity_id": "camera-1",
             "sections": [{"section_id": "left-shot"}]},
            {"track_id": "shot-track-2", "ced_type": "camera.cut",
             "binding_entity_id": "camera-2",
             "sections": [{"section_id": "right-shot"}]},
        ],
    }
    mapping = {
        "entities": {
            "CamLeft": {"actor_label": "CamLeftNative"},
            "CamRight": {"actor_label": "CamRightNative"},
        },
    }
    sampling = {
        "camera_cuts": [
            {"source_entity_id": "camera-1", "source_section_id": "left-shot",
             "start_frame": 0, "end_frame": 20, "status": "FRAME_ALIGNED"},
            {"source_entity_id": "camera-2", "source_section_id": "right-shot",
             "start_frame": 20, "end_frame": 40, "status": "FRAME_ALIGNED"},
        ],
    }
    target = {
        "camera_cut_sections": {
            "status": "OBSERVED",
            "binding_provenance": "NATIVE_SEQUENCE_CAMERA_BINDING_ID",
            "sections": [
                {"actor_label": "CamLeftNative", "start_frame": 0, "end_frame": 22},
                {"actor_label": "CamRightNative", "start_frame": 22, "end_frame": 40},
            ],
        },
    }
    bounded = {
        "status": "INVESTIGATE_APPROVED_NARROW_ADAPTER_OR_REPORT_LIMITATION",
        "repair_plan_sha256": "b" * 64,
    }
    native = {
        "native_attempt": {"native_builder_completed": True},
        "distinct_reopened_editor_observed": True,
        "camera_cuts_status": "FAIL",
        "camera_lens_status": "PASS",
        "readback_sha256": "c" * 64,
    }
    canonical = copy.deepcopy(job)
    state = {
        "job": job, "csir": csir, "mapping": mapping,
        "sampling": sampling, "target": target,
        "bounded": bounded, "native": native, "canonical": canonical,
    }
    monkeypatch.setattr(proof.outcome, "_context", lambda *_: (
        candidate.parents[1], candidate, canonical, csir, mapping, {},
    ))
    monkeypatch.setattr(proof.outcome, "discover", lambda *_: [folder])
    monkeypatch.setattr(proof.repair, "build", lambda *_: bounded)
    monkeypatch.setattr(proof.readback, "build", lambda *_: native)
    monkeypatch.setattr(proof.readback, "_safe_json", lambda p: (
        sampling if Path(p).name == "sampling-plan.json" else target,
        "d" * 64,
    ))
    return candidate.parents[1], job, state


def test_exact_two_camera_source_switch_proves_only_shared_boundary(
        tmp_path, monkeypatch):
    workspace, job, _ = scenario(monkeypatch, tmp_path)
    result = proof.build(workspace, job)
    assert result["kind"] == proof.KIND
    assert result["eligible"] is True
    assert result["camera_count"] == 2
    assert result["switch_count"] == 1
    assert result["maximum_frame_boundary_error"] == 2
    assert result["shots"][0]["expected_end_frame"] == 20
    assert result["shots"][0]["native_end_frame"] == 22
    assert result["shots"][1]["expected_start_frame"] == 20
    assert result["shots"][1]["native_start_frame"] == 22
    assert result["native_edit_authorized"] is False
    assert result["model_can_supply_frame_values"] is False
    assert result["full_cutscene_fidelity_verified"] is False
    assert result["two_shot_cut_repair_sha256"] == proof.single._hash({
        key: value for key, value in result.items()
        if key != "two_shot_cut_repair_sha256"
    })


@pytest.mark.parametrize("change,reason", [
    (lambda s: s["canonical"].update(job_id="f" * 32), "job changed"),
    (lambda s: s["sampling"]["camera_cuts"][0].update(end_frame=21),
     "contiguous"),
    (lambda s: s["target"]["camera_cut_sections"]["sections"][0].update(
        end_frame=21), "contiguous"),
    (lambda s: s["sampling"]["camera_cuts"][0].update(status="SUBFRAME"),
     "subframe"),
    (lambda s: s["target"]["camera_cut_sections"].update(
        binding_provenance="LABEL_GUESS"), "binding provenance"),
    (lambda s: s["native"].update(camera_cuts_status="PASS"), "discrepancy"),
    (lambda s: s["native"].update(camera_lens_status="INCOMPLETE"), "discrepancy"),
    (lambda s: s["native"].update(distinct_reopened_editor_observed=False),
     "discrepancy"),
    (lambda s: s["bounded"].update(
        status="STOP_MEASURED_REGRESSION_OR_NO_PROGRESS"), "discrepancy"),
    (lambda s: s["target"]["camera_cut_sections"]["sections"][0].update(
        end_frame=50), "contiguous"),
    (lambda s: (
        s["target"]["camera_cut_sections"]["sections"][0].update(end_frame=32),
        s["target"]["camera_cut_sections"]["sections"][1].update(start_frame=32),
    ), "too many"),
    (lambda s: s["sampling"]["camera_cuts"][0].update(start_frame=1),
     "Outer shot"),
    (lambda s: s["target"]["camera_cut_sections"]["sections"][1].update(
        end_frame=39), "Outer shot"),
    (lambda s: s["target"]["camera_cut_sections"]["sections"][0].update(
        actor_label="WrongNativeCamera"), "binding differs"),
    (lambda s: s["mapping"]["entities"]["CamLeft"].update(
        actor_label="WrongMappedCamera"), "binding differs"),
    (lambda s: s["csir"]["tracks"][0].update(muted=True), "ownership"),
    (lambda s: s["csir"]["tracks"][0].update(
        binding_entity_id="camera-2"), "ownership"),
    (lambda s: s["csir"]["tracks"].append(
        copy.deepcopy(s["csir"]["tracks"][0])), "ownership"),
    (lambda s: s["sampling"]["camera_cuts"].append(
        copy.deepcopy(s["sampling"]["camera_cuts"][0])), "two-shot"),
    (lambda s: s["target"]["camera_cut_sections"]["sections"].append(
        copy.deepcopy(s["target"]["camera_cut_sections"]["sections"][0])),
     "two-shot"),
])
def test_two_shot_refuses_unapproved_cameras_timings_and_evidence(
        tmp_path, monkeypatch, change, reason):
    workspace, job, state = scenario(monkeypatch, tmp_path)
    change(state)
    with pytest.raises(proof.TwoShotEvidenceError, match=reason):
        proof.build(workspace, job)


@pytest.mark.parametrize("message,expected", [
    ("Please fix the camera cut timing.", True),
    ("Correct both camera cut boundaries.", True),
    ("Restore the shot switch timing.", True),
    ("Don't change camera cut timing.", False),
    ("Please fix camera cut and zoom animation.", False),
    ("Fix camera cut and lens.", False),
    ("Fix the camera rotation and cut timing.", False),
    ("Fix all camera cuts in every scene.", False),
    ("Insert a new camera cut.", False),
    ("Correct three camera shots.", False),
    ("Fix the single camera cut.", False),
    ("Fix the character orientation.", False),
])
def test_exact_two_shot_user_request_scope(message, expected):
    assert proof.message_requests_two_shot(message) is expected


def test_two_shot_router_accepts_only_exact_hash_scoped_evidence(
        monkeypatch, tmp_path):
    workspace, job, _ = scenario(monkeypatch, tmp_path)
    ok = proof.build(workspace, job)
    options = {
        "generation_complete": True,
        "native_material_fallback_slots": 0,
        "source_albedo_provenance": False,
        "completed_repairs": 0, "repair_budget": 2,
        "independent_issues": [],
    }
    route = router.route("Please fix camera cut timing.",
                         two_shot_cut_repair_evidence=ok, **options)
    assert route["disposition"] == "GUARDED_TWO_SHOT_SWITCH_BOUNDARY_AVAILABLE"
    assert route["safe_strategies"] == [
        "report_only", "restore_two_shot_camera_switch",
    ]
    assert route["requires_editor_receipt"] is True
    assert route["model_can_authorize_native_commands"] is False
    for invalid in (
        {}, {"kind": "cutsceneai.studio.single_camera_cut_repair_review",
             **{k: v for k, v in ok.items() if k != "kind"}},
        dict(ok, eligible=False), dict(ok, camera_count=3),
        dict(ok, native_edit_authorized=True),
    ):
        unsafe = router.route(
            "Please fix camera cut timing.",
            two_shot_cut_repair_evidence=invalid, **options,
        )
        assert unsafe["safe_strategies"] == ["report_only"]
    limited = router.route(
        "Please fix camera cut timing.", two_shot_cut_repair_evidence=ok,
        **dict(options, completed_repairs=2),
    )
    assert limited["safe_strategies"] == ["report_only"]
