"""Element 6 single-use native execution claims: software-only fake engine tests.

These tests DO NOT run Unity or Unreal. Completion receipts are synthetic and
can only prove the correctness of the guarded file-queue contract.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for segment in ("packages/studio", "integrations/unreal", "tools", "tests/studio"):
    sys.path.insert(0, str(ROOT / segment))

import studio_element6_execution as guard
from test_element_studio_workflow import _setup, _write


def _queued(tmp_path):
    work, _worker, _target = _setup(tmp_path)
    candidate = json.loads((work / "active-candidate.json").read_text())
    config = json.loads((work / "connection.json").read_text())
    folder = work / "candidates" / candidate["candidate_id"]
    _write(folder / "session.json", {
        "kind": "cutsceneai.studio.prepared_transfer",
        "source": {"csir_path": config["csir"]},
        "target": {
            "mapping_path": candidate["mapping_copy"],
            "sequence_asset_path": candidate["sequence_path"],
            "project_path": config["target_project"],
        },
    })
    job_id = "a" * 32
    job = {
        "kind": "cutsceneai.studio.local_unreal_job",
        "schema_version": "0.1.0", "job_id": job_id,
        "candidate_id": candidate["candidate_id"],
        "candidate_dir": str(folder),
        "csir": config["csir"], "capture": config["capture"],
        "mapping": candidate["mapping_copy"],
        "sequence_path": candidate["sequence_path"],
        "expected_project": config["target_project"],
        "expected_level": config["level_path"],
        "create_level": False,
        "automatic_setup": False,
        "ai_agents_enabled": False,
        "ai_conversion_decision_sha256": "",
        "element_native_authorization_sha256": "",
        "generation_status": "NOT_STARTED",
        "status": "QUEUED", "fidelity_verified": False,
    }
    _write(work / "jobs" / (job_id + ".json"), job)
    _write(work / "active-job.json", {"job_id": job_id})
    return work, folder, job


def _receipt(folder, job, *, status="GENERATED_UNVERIFIED",
             stage="complete", plan_hash=None):
    transfer = plan_hash or hashlib.sha256(
        (folder / "transfer-plan.json").read_bytes()
    ).hexdigest()
    _write(folder / ("unreal-runtime-receipt-" + job["job_id"] + ".json"), {
        "kind": "cutsceneai.unreal.best_effort_receipt",
        "status": status, "stage": stage,
        "transfer_plan_sha256": transfer,
    })


def test_claim_is_durable_bound_and_one_native_attempt_only(tmp_path):
    work, folder, job = _queued(tmp_path)
    claim = guard.claim(work, job, editor_pid=943)
    assert claim["native_actions_executed"] is False
    assert claim["full_cutscene_fidelity_verified"] is False
    assert claim["native_attempt_index"] == 1
    assert claim["claim_sha256"] == guard.digest({
        k: v for k, v in claim.items() if k != "claim_sha256"
    })
    assert guard.load_claim(work, job, editor_pid=943) == claim
    with pytest.raises(guard.GuardedExecutionError, match="another Unreal Editor"):
        guard.load_claim(work, job, editor_pid=944)
    assert guard.inspect(work, job)["last_stage"] == "CLAIMED_NO_REPLAY"
    assert guard.inspect(work, job)["native_replay_allowed"] is False
    assert "CameraUnreal" not in json.dumps(claim)
    assert "Demo.uproject" not in json.dumps(claim)
    assert "Alice" not in json.dumps(claim)
    with pytest.raises(guard.GuardedExecutionError, match="already claimed"):
        guard.claim(work, job, editor_pid=944)
    assert len(list(folder.glob("element6-native-claim-*.json"))) == 1


def test_two_editor_processes_racing_only_one_can_claim(tmp_path):
    work, folder, job = _queued(tmp_path)
    outcomes = []
    barrier = threading.Barrier(2)

    def run(pid):
        barrier.wait(timeout=5)
        try:
            guard.claim(work, job, editor_pid=pid)
            outcomes.append("CLAIMED")
        except guard.GuardedExecutionError:
            outcomes.append("REFUSED")

    first = threading.Thread(target=run, args=(100,), daemon=True)
    second = threading.Thread(target=run, args=(200,), daemon=True)
    first.start()
    second.start()
    first.join(timeout=10)
    second.join(timeout=10)
    assert sorted(outcomes) == ["CLAIMED", "REFUSED"]
    assert len(list(folder.glob("element6-native-claim-*.json"))) == 1


def test_nonactive_queue_and_wrong_candidate_cannot_reach_native_worker(tmp_path):
    work, folder, job = _queued(tmp_path)
    _write(work / "active-job.json", {"job_id": "b" * 32})
    with pytest.raises(guard.GuardedExecutionError, match="active job"):
        guard.claim(work, job, editor_pid=123)
    assert not list(folder.glob("element6-native-claim-*.json"))
    _write(work / "active-job.json", {"job_id": job["job_id"]})
    bad = copy.deepcopy(job)
    bad["candidate_id"] = "20261121T183000Z_aaaaaaaa"
    with pytest.raises(guard.GuardedExecutionError, match="candidate"):
        guard.claim(work, bad, editor_pid=123)
    assert not list(folder.glob("element6-native-claim-*.json"))


def test_source_mapping_plan_or_approval_change_invalidates_live_attempt(tmp_path):
    for changed in ("csir", "mapping", "plan", "approval"):
        case = tmp_path / changed
        case.mkdir()
        work, folder, job = _queued(case)
        approval = folder / "element-native-approval.json"
        if changed == "approval":
            _write(approval, {"authorization_sha256": "c" * 64})
            job["element_native_authorization_sha256"] = "c" * 64
            _write(work / "jobs" / (job["job_id"] + ".json"), job)
        claim = guard.claim(work, job, editor_pid=994)
        assert guard.load_claim(work, job, editor_pid=994) == claim
        if changed == "plan":
            path = folder / "transfer-plan.json"
        elif changed == "approval":
            path = approval
        else:
            path = Path(job[changed])
        path.write_text(path.read_text(encoding="utf-8") + "\n",
                        encoding="utf-8")
        with pytest.raises(guard.GuardedExecutionError, match="changed"):
            guard.load_claim(work, job, editor_pid=994)
        assert guard.inspect(work, job)["native_replay_allowed"] is False


def test_structured_stage_checkpoints_are_ordered_and_never_overwritten(tmp_path):
    work, folder, job = _queued(tmp_path)
    claim = guard.claim(work, job, editor_pid=123)
    with pytest.raises(guard.GuardedExecutionError, match="missing earlier"):
        guard.step(work, job, claim, "NATIVE_SEQUENCE_BUILDER_STARTED")
    for index, stage in enumerate(guard.STAGES[1:-1], 1):
        saved = guard.step(work, job, claim, stage)
        assert saved["stage_index"] == index
    assert guard.inspect(work, job)["stages"] == list(guard.STAGES[1:-1])
    with pytest.raises(guard.GuardedExecutionError, match="repeated"):
        guard.step(work, job, claim, guard.STAGES[1])
    path = folder / ("element6-native-stage-" + job["job_id"] + "-02.json")
    forged = json.loads(path.read_text())
    forged["stage"] = "NATIVE_FIDELITY_PROVEN"
    forged["stage_sha256"] = guard.digest({
        k: v for k, v in forged.items() if k != "stage_sha256"
    })
    _write(path, forged)
    with pytest.raises(guard.GuardedExecutionError, match="does not match|altered"):
        guard.inspect(work, job)


def test_builder_receipt_is_not_engine_fidelity_or_individual_action_parity(tmp_path):
    work, folder, job = _queued(tmp_path)
    original_queued_job = copy.deepcopy(job)
    claim = guard.claim(work, job, editor_pid=123)
    for stage in guard.STAGES[1:]:
        guard.step(work, job, claim, stage)
    _receipt(folder, job)
    job["status"] = "GENERATED_AND_MEASURED_NOT_FIDELITY_VERIFIED"
    job["generation_status"] = "GENERATED_UNVERIFIED"
    result = guard.terminal(work, job, claim)
    assert result["status"] == (
        "NATIVE_BUILDER_COMPLETED_READBACK_AND_FIDELITY_UNVERIFIED"
    )
    assert result["native_builder_completed"] is True
    assert result["individual_native_action_readbacks_verified"] is False
    assert result["full_cutscene_fidelity_verified"] is False
    assert result["requires_manual_inspection"] is False
    info = guard.inspect(work, job)
    assert info["status"] == result["status"]
    assert info["native_replay_allowed"] is False
    with pytest.raises(guard.GuardedExecutionError, match="already claimed"):
        guard.terminal(work, job, claim)
    with pytest.raises(guard.GuardedExecutionError, match="already claimed"):
        guard.claim(work, original_queued_job, editor_pid=124)


@pytest.mark.parametrize("receipt_values", [
    None,
    {"status": "BLOCKED", "stage": "complete"},
    {"status": "GENERATED_UNVERIFIED", "stage": "incomplete"},
    {"status": "GENERATED_UNVERIFIED", "stage": "complete",
     "plan_hash": "f" * 64},
])
def test_failure_or_missing_runtime_proof_never_claims_builder_success(
        tmp_path, receipt_values):
    work, folder, job = _queued(tmp_path)
    claim = guard.claim(work, job, editor_pid=123)
    if receipt_values is not None:
        _receipt(folder, job, **receipt_values)
    job["status"] = "BLOCKED_OR_FAILED"
    job["generation_status"] = "NOT_STARTED"
    result = guard.terminal(work, job, claim)
    assert result["status"] == "INCOMPLETE_OR_FAILED_NO_AUTOMATIC_REPLAY"
    assert result["requires_manual_inspection"] is True
    assert result["native_builder_completed"] is False
    assert guard.inspect(work, job)["native_replay_allowed"] is False


def test_read_only_studio_job_status_surfaces_stale_heartbeat_as_unobservable(tmp_path):
    import studio_local_bridge as bridge

    work, _folder, job = _queued(tmp_path)
    guard.claim(work, job, editor_pid=123)
    job["status"] = "RUNNING"
    _write(work / "jobs" / (job["job_id"] + ".json"), job)
    response = bridge.job_status(job["job_id"], work)
    assert response["element6_execution"]["available"] is True
    assert response["element6_execution"]["status"] == (
        "NATIVE_ATTEMPT_UNOBSERVABLE_INSPECT_BEFORE_RECOVERY"
    )
    assert response["element6_execution"]["native_replay_allowed"] is False
    assert response["element6_execution"]["requires_manual_inspection"] is True


def test_native_worker_claim_is_before_any_editor_mutation_or_active_execution():
    worker = (ROOT / "integrations" / "unreal" /
              "studio_local_editor_worker.py").read_text(encoding="utf-8")
    assert worker.index("native_guard.claim(") < worker.index("job = _execute(job)")
    part = worker[worker.index("def _execute(job):"):
                  worker.index("def _update_destination_readiness():")]
    assert part.index("element6_guard.load_claim(") < part.index(
        "_ensure_target_level(job)"
    )
    assert part.index("element6_guard.step(") < part.index(
        "_ensure_target_level(job)"
    )
    assert part.index("studio_element_native_gate.verify_job(") < part.index(
        "_ensure_target_level(job)"
    )
    assert part.index("'DESTINATION_MUTATION_STARTED'") < part.index(
        "studio_character_execution.begin("
    )
    sync = (ROOT / "integrations" / "unreal" /
            "studio_planner_sync.py").read_text(encoding="utf-8")
    assert '("studio_element6_execution", "packages/studio")' in sync


@pytest.mark.parametrize("interrupted_after", range(len(guard.STAGES)))
def test_phase10_4_interrupt_each_guarded_native_checkpoint_never_replays(
        tmp_path, interrupted_after):
    """Simulate a worker dying after every durable native stage, including claim.

    A new editor must inspect the original incomplete attempt, never requeue
    an import, overwrite a checkpoint or mark an unobserved scene as verified.
    """
    work, folder, job = _queued(tmp_path)
    editor_pid = 2000 + interrupted_after
    claim = guard.claim(work, job, editor_pid=editor_pid)
    for stage in guard.STAGES[1:interrupted_after+1]:
        guard.step(work, job, claim, stage)
    before = sorted(p.name for p in folder.glob("element6-native-*.json"))
    report = guard.inspect(work, job)
    assert report["last_stage"] == guard.STAGES[interrupted_after]
    assert report["native_replay_allowed"] is False
    assert report["full_cutscene_fidelity_verified"] is False
    assert report["native_builder_completed"] is False
    assert report["status"] == (
        "ATTEMPT_IN_PROGRESS_OR_INTERRUPTED_INSPECT_BEFORE_ANY_RECOVERY"
    )
    with pytest.raises(guard.GuardedExecutionError, match="another Unreal Editor"):
        guard.load_claim(work, job, editor_pid=editor_pid+1)
    with pytest.raises(guard.GuardedExecutionError, match="already claimed"):
        guard.claim(work, job, editor_pid=editor_pid+1)
    if interrupted_after:
        with pytest.raises(guard.GuardedExecutionError, match="repeated"):
            guard.step(work, job, claim, guard.STAGES[interrupted_after])
    assert sorted(p.name for p in folder.glob("element6-native-*.json")) == before
