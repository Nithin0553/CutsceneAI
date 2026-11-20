"""Software-only integrated Unity-evidence -> AI -> Unreal receipt -> release smoke.

The Unreal API and OpenAI Responses transport are mocked. Real editor save/
reopen and cross-engine fidelity are intentionally NEVER claimed by this test.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[2]
for folder in ("tools", "packages/studio", "packages/cinetwin", "integrations/unreal"):
    sys.path.insert(0, str(ROOT / folder))

import animation_conversion_policy as policy
import sampling_plan
import studio_ai_transfer_audit as ai_audit
import studio_character_execution as character_executor
import studio_local_bridge as bridge
import studio_release_gate as release_gate
from test_character_animation_policy import (
    Asset,
    _choice,
    _json,
    _probe,
    _read,
    case,
)

# Re-export Friday's synthetic fixture to keep the integrated workflow on
# the same validated source/target contract without duplicating setup.
__all__ = ["case"]

def _fake_native_character_readback(case, job, candidate, selected, plan):
    """Exercise the REAL native readback validator against a small Unreal mock."""
    clip = Asset(case.clip_path, "AnimSequence", skeleton=case.target_skeleton, duration=1.0)
    case.assets[case.clip_path] = clip
    actor = Asset("/Game/Staging/Actor", "SkeletalMeshActor",
                  skeletal_mesh_component=NS(get_skeletal_mesh_asset=lambda: case.assets[case.profile["target_mesh_path"]]))
    actor.get_actor_label = lambda: "NewPerformer"
    actor.get_path_name = lambda: "/Game/Staging/Actor.Actor"
    actor.get_components_by_class = lambda _: []
    params = NS(get_editor_property=lambda name: {
        "animation": clip,
        "start_frame_offset": NS(value=0),
        "play_rate": NS(to_fixed_play_rate=lambda: 1.0),
    }[name])
    section = NS(get_editor_property=lambda _: params)
    track = case.api.MovieSceneSkeletalAnimationTrack()
    track.get_sections = lambda: [section]
    binding = NS(get_tracks=lambda: [track])
    case.api.MovieSceneSequenceExtensions = NS(
        get_bindings=lambda _: [binding],
        locate_bound_objects=lambda *_: [actor],
        get_tick_resolution=lambda _: NS(numerator=24000, denominator=1),
    )
    case.api.MovieSceneSectionExtensions = NS(
        get_start_frame=lambda _: 0, get_end_frame=lambda _: 24,
    )
    case.api.UnrealEditorSubsystem = object()
    case.api.get_editor_subsystem = lambda _: NS(
        get_all_level_actors=lambda: [actor], get_editor_world=object,
    )
    output = character_executor.record(
        case.api, job, plan, selected,
        Asset(job["sequence_path"], "LevelSequence"),
        path=candidate / policy.NATIVE_FILE,
    )
    return output


def test_synthetic_transfer_reaches_native_receipt_but_not_fidelity(case, tmp_path, monkeypatch):
    # 1. The Unity extraction/Play Mode evidence obeys the canonical frame grid.
    planned = sampling_plan.build_plan(
        case.csir, csir_sha256=hashlib.sha256(
            Path(case.config["csir"]).read_bytes()
        ).hexdigest(),
    )
    assert not sampling_plan.validate_capture(planned, case.capture)["failures"]

    # 2. Native Unreal target probe and production OpenAI schema are exercised
    #    with mock Editor assets/transport. The model never sees paths.
    report, decision = _choice(case, monkeypatch)
    selected, = [row for row in report["characters"] if row["id"] == "character-01"]
    assert selected["status"] == "COMPATIBLE_AFTER_APPROVED_RETARGET"
    assert decision["model_provider"] == "OPENAI_RESPONSES"
    assert decision["animation_conversion"]["action_id"] == policy.ACTION

    # 3. The normal Studio backend prepares and queues the exact immutable plan.
    workspace = tmp_path / "runs"
    connection = bridge.config_check({
        **case.config, "source_rights_confirmed": True,
        "skeletal_root_world_lock": False,
    })
    _json(workspace / "connection.json", connection)
    _json(workspace / policy.PROBE_RESULT, _probe(case))
    ready = bridge.prepare(
        workspace, {
            "source_feature_surface_path": case.census,
            "require_complete_source_features": False,
        },
        character_selection=(report, decision["animation_conversion"]),
    )
    candidate = Path(ready["candidate_dir"])
    _json(candidate / policy.REPORT_FILE, report)
    _json(candidate / "ai-conversion-decision.json", decision)
    bridge.approve_one_click(ready["candidate_id"], workspace, enable_ai_agents=True)
    worker = {
        **case.worker, "worker_version": bridge.REQUIRED_WORKER_PROTOCOL,
        "checkout_root": str(ROOT),
        "worker_source_sha256": hashlib.sha256(
            (ROOT / "integrations/unreal/studio_local_editor_worker.py").read_bytes()
        ).hexdigest(),
    }
    monkeypatch.setattr(bridge, "worker_connected", lambda _: worker)
    monkeypatch.setattr(bridge, "destination_readiness", lambda _: {
        "ready": False, "status": "SCENE_SETUP_REQUIRED",
    })
    queued = bridge.queue_trial(ready["candidate_id"], workspace)
    job_path = workspace / "jobs" / (queued["job_id"] + ".json")
    job = _read(job_path)
    plan = _read(candidate / "transfer-plan.json")
    assert plan["ai_character_animation"] == decision["animation_conversion"]
    assert job["automatic_setup"] is True

    # 4. A model decision/queued job alone is NOT successful native generation.
    before = ai_audit.assess(workspace, job["job_id"])
    assert before["model_decision_recorded"] is True
    assert before["native_builder_completed"] is False
    assert before["character_conversion"]["native_readback_passed"] is False

    # 5. Explicitly SYNTHETIC native receipt and mocked engine readback.
    #    The production audit requires both, tied to the submitted job.
    generated = job["sequence_path"] + "." + job["sequence_path"].rsplit("/", 1)[-1]
    native = _fake_native_character_readback(case, job, candidate, selected, plan)
    assert native["status"] == "PASS", native
    receipt = candidate / ("unreal-runtime-receipt-" + job["job_id"] + ".json")
    _json(receipt, {
        "kind": "cutsceneai.unreal.best_effort_receipt",
        "status": "GENERATED_UNVERIFIED",
        "stage": "complete",
        "verified_project": job["expected_project"],
        "verified_level": job["expected_level"],
        "transfer_plan_sha256": hashlib.sha256(
            (candidate / "transfer-plan.json").read_bytes()
        ).hexdigest(),
        "generated_sequence": generated,
    })
    job.update(
        status="GENERATED_AND_MEASURED_NOT_FIDELITY_VERIFIED",
        generation_status="GENERATED_UNVERIFIED",
        generated_sequence=generated,
        receipt_file=str(receipt),
        character_native_readback_status="PASS",
    )
    _json(job_path, job)
    assessed = ai_audit.assess(workspace, job["job_id"])
    assert assessed["native_builder_completed"] is True
    assert assessed["character_conversion"]["native_readback_passed"] is True
    assert assessed["fidelity_verified"] is False

    gated = release_gate.assess(workspace, job["job_id"])
    assert gated["checks"]["native_generation"]["status"] == "PASS"
    assert gated["checks"]["independent_editor_restart"]["status"] == "INCOMPLETE"
    assert gated["checks"]["ai_pretransfer_planning"]["status"] == "INCOMPLETE"
    assert gated["release_ready"] is False

    # 6. A changed decision after the native receipt must invalidate the audit.
    changed = _read(candidate / "ai-conversion-decision.json")
    changed["reason"] = "tampered after queue"
    _json(candidate / "ai-conversion-decision.json", changed)
    with pytest.raises(ai_audit.AITransferAuditError, match="bytes differ"):
        ai_audit.assess(workspace, job["job_id"])
    assert release_gate.assess(workspace, job["job_id"])["checks"][
        "ai_pretransfer_planning"
    ]["status"] == "FAIL"
