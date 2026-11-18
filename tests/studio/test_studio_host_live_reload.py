"""Software-only Studio localhost hot-restart watcher safety tests."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "tools/studio_host_live_reload.py"
spec = importlib.util.spec_from_file_location("_studio_host_live_reload_test", MODULE)
assert spec is not None and spec.loader is not None
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)


def _checkout(tmp_path):
    root = tmp_path / "repo"
    for directory in watch.DIRECTORIES:
        (root / directory).mkdir(parents=True)
    code = root / "tools/studio_local_bridge.py"
    code.write_text("VERSION = 1\n", encoding="utf-8")
    workspace = tmp_path / "runs"
    workspace.mkdir()
    return root, workspace, code


def test_valid_changes_request_only_local_server_reload_after_stable_observation(tmp_path):
    root, workspace, code = _checkout(tmp_path)
    observer = watch.HostCodeWatcher(root, workspace)
    assert observer.observe() is False
    code.write_text("VERSION = 2\n", encoding="utf-8")
    assert observer.observe() is False
    assert observer.status()["status"] == "VALIDATING_UPDATE"
    assert observer.observe() is True
    status = observer.status()
    assert status["status"] == "READY_TO_RELOAD"
    assert status["engine_restart_required"] is False
    assert status["native_job_replayed"] is False


def test_active_autopilot_stage_prevents_host_replacement(tmp_path):
    root, workspace, code = _checkout(tmp_path)
    observer = watch.HostCodeWatcher(root, workspace)
    code.write_text("VERSION = 2\n")
    (workspace / "autopilot-active.json").write_text(json.dumps({
        "status": "PREPARING", "message": "Preparing immutable source evidence.",
    }))
    observer.observe()
    assert observer.observe() is False
    assert observer.status()["status"] == "DEFERRED_ACTIVE_TRANSFER"


def test_orphaned_unreal_running_status_cannot_be_lost_during_host_update(tmp_path):
    root, workspace, code = _checkout(tmp_path)
    observer = watch.HostCodeWatcher(root, workspace)
    code.write_text("VERSION = 2\n")
    (workspace / "autopilot-active.json").write_text(json.dumps({
        "status": "UNREAL_RUNNING", "job_id": "a" * 32,
    }))
    observer.observe()
    assert observer.observe() is False
    assert observer.status()["status"] == "DEFERRED_ACTIVE_TRANSFER"


def test_queued_or_running_native_jobs_prevent_host_reload(tmp_path):
    for status in ("QUEUED", "RUNNING"):
        root, workspace, code = _checkout(tmp_path / status)
        observer = watch.HostCodeWatcher(root, workspace)
        code.write_text("VERSION = 2\n")
        jobs = workspace / "jobs"
        jobs.mkdir()
        (jobs / ("a" * 32 + ".json")).write_text(json.dumps({
            "job_id": "a" * 32, "status": status,
        }))
        observer.observe()
        assert observer.observe() is False
        assert observer.status()["status"] == "DEFERRED_ACTIVE_TRANSFER"


def test_invalid_python_update_never_restarts_host_or_any_editor(tmp_path):
    root, workspace, code = _checkout(tmp_path)
    observer = watch.HostCodeWatcher(root, workspace)
    code.write_text("def invalid(:\n", encoding="utf-8")
    assert observer.observe() is False
    assert observer.status()["status"] == "BLOCKED_INVALID_CODE"
    assert observer.mutation_safe() is False


def test_studio_source_watcher_never_directly_restarts_unreal_or_unity():
    source = MODULE.read_text(encoding="utf-8")
    for prohibited in ("import unreal", "EditorApplication.", "subprocess.Popen(", "os.system(", "queue_trial("):
        assert prohibited not in source
