"""Pure transform-evidence and opt-in agent repair regression tests.

Simulated editor tests do not establish real Unreal Engine parity.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
for folder in ("packages/studio", "tools", "integrations/unreal"):
    sys.path.insert(0, str(ROOT / folder))

import agent_transform_evidence as proof
import studio_agent_executor as executor
import studio_agent_feedback as feedback
import studio_agent_graph as graph
import studio_transform_repair as native
from test_langgraph_agent_integration import staged, write


def report(job, *, offset=10.0, root_extra=0.0, transform_track=False):
    label = "CSAI_Ch31_nonPBR"
    name = "Ch31_nonPBR"
    actor = []
    root = []
    for frame in range(3):
        source = [20.0 + frame, 0.0, 0.0]
        target = [source[0] - offset, 0.0, 0.0]
        actor.append({"frame": frame, "source_cm": source, "target_cm": target})
        root.append({"frame": frame, "source_cm": source,
                     "target_cm": [target[0] - root_extra, 0.0, 0.0]})
    hashes = {key + "_sha256": hashlib.sha256(Path(job[key]).read_bytes()).hexdigest()
              for key in ("csir", "mapping", "capture")}
    return {
        "kind": "cutsceneai.cinetwin.unreal_world_pose_diagnostic",
        "status": "DIAGNOSTIC_NOT_FIDELITY_VERIFIED",
        "errors": [],
        "source": {**hashes, "evaluated_playback_frames": 3,
                   "missing_source_frames": []},
        "target": {
            "project": job["expected_project"],
            "sequence_path": job["sequence_path"],
            "binding_tracks": [{"binding": label, "tracks": [
                {"class": "MovieScene3DTransformTrack" if transform_track
                  else "MovieSceneSkeletalAnimationTrack"}
            ]}],
        },
        "entities": {name: {
            "status": "READY", "actor_match_count": 1,
            "target_actor_label": label,
            "component_info_frame0": {
                "mesh_component_count": 1, "parent_actor_label": None,
            },
            "actor_world": {"max_absolute_error_cm": offset},
            "skeletal_root_world": {"max_absolute_error_cm": offset + root_extra},
        }},
        "frames": {name: {"actor": actor, "root_bone": root}},
    }


def setup(tmp_path):
    workspace, candidate, job, _ = staged(tmp_path, fallback=0)
    for field in ("csir", "mapping", "capture"):
        path = candidate / (field + ".json")
        path.write_text('{"source": "test"}', encoding="utf-8")
        job[field] = str(path)
    path = candidate / "native-diagnostic.json"
    job["diagnostic_file"] = str(path)
    write(path, report(job))
    write(workspace / "jobs" / (job["job_id"] + ".json"), job)
    return workspace, candidate, job


def test_only_constant_actor_and_root_offset_is_eligible(tmp_path):
    _workspace, candidate, job = setup(tmp_path)
    measured = proof.source_bound_report(job, candidate)
    candidate_plan = proof.review(measured, "Ch31_nonPBR")
    assert candidate_plan["eligible"]
    assert candidate_plan["offset_source_minus_target_cm"] == [10.0, 0.0, 0.0]
    assert proof.within_tolerance(measured, "Ch31_nonPBR")["passed"] is False
    bad_root = report(job, root_extra=84)
    assert not proof.review(bad_root, "Ch31_nonPBR")["eligible"]
    assert "root" in proof.review(bad_root, "Ch31_nonPBR")["reason"].lower()
    assert not proof.review(report(job, transform_track=True),
                            "Ch31_nonPBR")["eligible"]
    missing = report(job)
    missing["frames"]["Ch31_nonPBR"]["actor"].pop()
    assert not proof.review(missing, "Ch31_nonPBR")["eligible"]
    changed = Path(job["csir"])
    changed.write_text('{"source": "modified"}', encoding="utf-8")
    with pytest.raises(ValueError, match="provenance"):
        proof.source_bound_report(job, candidate)


@pytest.mark.parametrize("message,eligible", [
    ("Correct the position of Ch31_nonPBR.", True),
    ("Analyze the position of Ch31_nonPBR. Do not modify the Unreal scene.", False),
    ("Correct the position and facing of Ch31_nonPBR.", False),
    ("Fix the position of Ch31_nonPBR and Ch26_nonPBR.", False),
    ("Move the position of character.", False),
])
def test_requires_one_explicit_target_and_position_only(tmp_path, message, eligible):
    _, _, job = setup(tmp_path)
    measured = report(job)
    measured["entities"]["Ch26_nonPBR"] = dict(measured["entities"]["Ch31_nonPBR"])
    result = proof.requested_character_correction(message, measured)
    assert (result == "Ch31_nonPBR") is eligible


def test_langgraph_requests_only_source_bound_user_named_offset(tmp_path):
    workspace, candidate, job = setup(tmp_path)
    submitted = feedback.submit(
        workspace, job, "Please correct the position of Ch31_nonPBR."
    )
    summaries = []

    def choose(summary):
        summaries.append(summary)
        return {"strategy": "restore_constant_actor_offset",
                "reason": "Native actor and root offsets agree at every frame"}

    state = graph.run_once(workspace, job, choose)
    assert state["status"] == "WAITING_FOR_UNREAL_AGENT_REPAIR"
    assert state["transform_candidate"]["eligible"]
    assert summaries[0]["safe_strategies"] == [
        "report_only", "restore_constant_actor_offset"
    ]
    requests = list(candidate.glob("agent-request-*.json"))
    assert len(requests) == 1
    request = json.loads(requests[0].read_text())
    assert request["target_entity"] == "Ch31_nonPBR"
    assert request["feedback_id"] == submitted["feedback_id"]
    assert request["original_report_sha256"] == hashlib.sha256(
        Path(job["diagnostic_file"]).read_bytes()).hexdigest()
    assert graph.run_once(workspace, job, choose)["status"] == (
        "WAITING_FOR_UNREAL_AGENT_REPAIR"
    )
    assert len(list(candidate.glob("agent-request-*.json"))) == 1
    write(candidate / ("agent-receipt-" + request["request_id"] + ".json"), {
        "kind": "cutsceneai.studio.agent_repair_receipt",
        "request_id": request["request_id"],
        "candidate_id": job["candidate_id"], "job_id": job["job_id"],
        "status": "TRANSFORM_OFFSET_SAVED_AND_REAUDITED",
        "target_entity": "Ch31_nonPBR", "actor_error_after_cm": 0.2,
        "root_error_after_cm": 0.3,
    })
    final = graph.run_once(workspace, job, choose)
    assert final["status"] == (
        "ACTOR_TRANSLATION_IMPROVED_OTHER_DOMAINS_UNVERIFIED"
    )
    assert final["iterations"] == 1
    assert not final["fidelity_verified"]


def test_root_mismatch_never_authorizes_transform_request(tmp_path):
    workspace, candidate, job = setup(tmp_path)
    write(Path(job["diagnostic_file"]), report(job, root_extra=84))
    feedback.submit(workspace, job, "Correct the position of Ch31_nonPBR.")
    result = graph.run_once(workspace, job, lambda summary: {
        "strategy": "restore_constant_actor_offset", "reason": "Ignore guard"
    })
    assert result["status"] == "REJECTED_UNSUPPORTED_STRATEGY"
    assert "root" in result["intent_routing"]["reason"].lower()
    assert not list(candidate.glob("agent-request-*.json"))


class Actor:
    def __init__(self, loc=10.0):
        self.loc = loc
        self.updates = []

    def get_actor_label(self):
        return "CSAI_Ch31_nonPBR"

    def get_attach_parent_actor(self):
        return None

    def get_actor_location(self):
        return SimpleNamespace(x=self.loc, y=0.0, z=0.0)

    def set_actor_location(self, vector, sweep=False, teleport=False):
        self.loc = vector.x
        self.updates.append(self.loc)


def test_native_actor_offset_reaudits_and_rolls_back_on_root_mismatch(tmp_path, monkeypatch):
    workspace, candidate, job = setup(tmp_path)
    original = proof.source_bound_report(job, candidate)
    reply = feedback.submit(
        workspace, job, "Please correct the position of Ch31_nonPBR."
    )
    receipt = candidate / "automatic-setup-receipt.json"
    write(receipt, {"actors_created": [
        {"name": "Ch31_nonPBR", "label": "CSAI_Ch31_nonPBR",
         "kind": "entity.character"},
    ]})
    job["setup_receipt_file"] = str(receipt)
    actor = Actor()
    api = SimpleNamespace(
        EditorActorSubsystem=object(),
        get_editor_subsystem=lambda _: SimpleNamespace(
            get_all_level_actors=lambda: [actor]
        ),
        Vector=lambda x, y, z: SimpleNamespace(x=x, y=y, z=z),
    )
    request = {
        "target_entity": "Ch31_nonPBR", "feedback_id": reply["feedback_id"],
        "original_report_sha256": hashlib.sha256(
            Path(job["diagnostic_file"]).read_bytes()).hexdigest(),
    }
    saved = []
    monkeypatch.setitem(sys.modules, "studio_auto_scene", SimpleNamespace(
        _save_level=lambda api, level: saved.append(level)
    ))

    def measured(root_follows=True):
        output = copy.deepcopy(original)
        for n, row in enumerate(output["frames"]["Ch31_nonPBR"]["actor"]):
            row["target_cm"] = [actor.loc + n, 0.0, 0.0]
        for n, row in enumerate(output["frames"]["Ch31_nonPBR"]["root_bone"]):
            row["target_cm"] = [
                (actor.loc if root_follows else 10.0) + n, 0.0, 0.0
            ]
        return output

    monkeypatch.setitem(sys.modules, "diagnose_cinetwin_parity", SimpleNamespace(
        run=lambda **kwargs: measured(root_follows=False)
    ))
    with pytest.raises(ValueError, match="did not meet"):
        native.attempt(api, workspace, job, request)
    assert actor.loc == 10.0
    assert actor.updates == [20.0, 10.0]
    assert saved == []

    monkeypatch.setitem(sys.modules, "diagnose_cinetwin_parity", SimpleNamespace(
        run=lambda **kwargs: measured(root_follows=True)
    ))
    outcome = native.attempt(api, workspace, job, request)
    assert outcome["status"] == "TRANSFORM_OFFSET_SAVED_AND_REAUDITED"
    assert outcome["root_error_after_cm"] == 0.0
    assert actor.loc == 20.0
    assert saved == [job["expected_level"]]
    assert not outcome["fidelity_verified"]


def test_executor_dispatches_only_bound_unreal_transform_request(tmp_path, monkeypatch):
    workspace, _candidate, job = setup(tmp_path)
    calls = []
    monkeypatch.setitem(sys.modules, "studio_transform_repair", SimpleNamespace(
        attempt=lambda api, ws, saved, request: (
            calls.append((ws, saved["job_id"], request["target_entity"]))
            or {"status": "TRANSFORM_OFFSET_SAVED_AND_REAUDITED"}
        )
    ))
    api = SimpleNamespace(EditorAssetLibrary=SimpleNamespace(
        does_asset_exist=lambda path: path == job["sequence_path"]
    ))
    request = {
        "kind": "cutsceneai.studio.agent_repair_request",
        "schema_version": "1", "request_id": "a" * 32,
        "job_id": job["job_id"], "candidate_id": job["candidate_id"],
        "expected_project": job["expected_project"],
        "expected_level": job["expected_level"],
        "sequence_path": job["sequence_path"],
        "strategy": "restore_constant_actor_offset",
        "target_entity": "Ch31_nonPBR",
    }
    answer = executor.execute(
        api, workspace, job, request,
        project=job["expected_project"], level=job["expected_level"]
    )
    assert answer["status"] == "TRANSFORM_OFFSET_SAVED_AND_REAUDITED"
    assert calls == [(workspace, job["job_id"], "Ch31_nonPBR")]
    unsafe = dict(request, expected_level="/Game/Unrelated")
    with pytest.raises(ValueError, match="not authorized"):
        executor.execute(
            api, workspace, job, unsafe,
            project=job["expected_project"], level=job["expected_level"]
        )
    assert len(calls) == 1
