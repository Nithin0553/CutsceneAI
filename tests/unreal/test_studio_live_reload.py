"""Simulated persistent Unreal Python worker reload without starting Unreal."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "integrations/unreal/studio_local_editor_worker.py"


@pytest.fixture
def worker(tmp_path, monkeypatch):
    source = tmp_path / "integrations/unreal/studio_local_editor_worker.py"
    source.parent.mkdir(parents=True)
    source.write_bytes(WORKER.read_bytes())
    state = {"callbacks": [], "removed": [], "logs": []}
    api = NS(
        register_slate_post_tick_callback=lambda handler: state["callbacks"].append(handler) or len(state["callbacks"]),
        unregister_slate_post_tick_callback=lambda handle: state["removed"].append(handle),
        log=lambda value: state["logs"].append(str(value)),
        log_warning=lambda value: state["logs"].append(str(value)),
        log_error=lambda value: state["logs"].append(str(value)),
    )
    monkeypatch.setitem(sys.modules, "unreal", api)
    name = "_cutsceneai_live_worker_unreal_test"
    spec = importlib.util.spec_from_file_location(name, source)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, mod)
    spec.loader.exec_module(mod)
    mod.WORKSPACE = tmp_path / "runs"
    return mod, source, state


def _update(source):
    source.write_text(source.read_text() + "\nAUTO_RELOAD_REGRESSION_MARKER = 42\n")


def test_running_unreal_worker_refreshes_changed_python_without_editor_restart(worker):
    mod, source, state = worker
    mod.start()
    handler = state["callbacks"][0]
    old_handle = mod.HANDLE
    original_workspace = mod.WORKSPACE
    old_hash = mod.WORKER_SOURCE_SHA256
    _update(source)
    assert mod._refresh_worker_python() is True
    assert mod.HANDLE == old_handle
    assert mod.WORKSPACE == original_workspace
    assert mod.WORKER_SOURCE_SHA256 != old_hash
    assert mod.WORKER_SOURCE_SHA256 == hashlib.sha256(source.read_bytes()).hexdigest()
    assert mod.AUTO_RELOAD_REGRESSION_MARKER == 42
    assert mod.LIVE_RELOAD_STATE == "AUTO_RELOADED"
    assert len(state["callbacks"]) == 1 and state["removed"] == []
    # Original callback delegates into *new* module code even after exec.
    invoked = []
    mod._tick = lambda value: invoked.append(value)
    handler(5)
    assert invoked == [5]
    mod.start()
    assert len(state["callbacks"]) == 1
    mod.stop()
    assert state["removed"] == [old_handle]


def test_native_busy_refresh_defers_without_losing_original_worker(worker):
    mod, source, _state = worker
    mod.BUSY = True
    _update(source)
    old_hash = mod.WORKER_SOURCE_SHA256
    assert mod._refresh_worker_python() is True
    assert mod.LIVE_RELOAD_STATE == "DEFERRED_NATIVE_JOB"
    assert mod.WORKER_SOURCE_SHA256 == old_hash
    assert not hasattr(mod, "AUTO_RELOAD_REGRESSION_MARKER")


def test_orphaned_running_native_job_prevents_new_code_execution(worker):
    mod, source, _state = worker
    jobs = mod.WORKSPACE / "jobs"
    jobs.mkdir(parents=True)
    (jobs / ("a" * 32 + ".json")).write_text(json.dumps({
        "status": "RUNNING", "job_id": "a" * 32,
    }))
    _update(source)
    assert mod._refresh_worker_python() is True
    assert mod.LIVE_RELOAD_STATE == "DEFERRED_NATIVE_JOB"
    assert mod.WORKER_SOURCE_SHA256 != hashlib.sha256(source.read_bytes()).hexdigest()


def test_invalid_python_update_never_claims_a_new_worker_version(worker):
    mod, source, state = worker
    old_hash = mod.WORKER_SOURCE_SHA256
    source.write_text(source.read_text() + "\ndef not_valid(:\n")
    assert mod._refresh_worker_python() is True
    assert mod.LIVE_RELOAD_STATE == "BLOCKED"
    assert mod.WORKER_SOURCE_SHA256 == old_hash
    assert any("blocked" in message for message in state["logs"])


def test_unchanged_code_does_not_interrupt_editor_tick(worker):
    mod, _source, state = worker
    assert mod._refresh_worker_python() is False
    assert mod.LIVE_RELOAD_STATE == "CURRENT"
    assert not state["callbacks"]


def test_auto_refresh_does_not_perform_asset_or_level_mutations():
    source = WORKER.read_text()
    assert "register_slate_post_tick_callback(_tick_dispatch)" in source
    before_refresh = source.split("def _refresh_worker_python():")[1].split("def _tick_dispatch(")[0]
    for operation in ("delete_asset(", "save_loaded_asset(", "_ensure_target_level(", "build_prepared_files(", "queue_trial("):
        assert operation not in before_refresh


def test_changed_trusted_adapter_is_refreshed_while_editor_remains_open(worker, monkeypatch):
    mod, source, _state = worker
    dependency = source.parents[2] / "packages/studio/adapter_example.py"
    dependency.parent.mkdir(parents=True)
    dependency.write_text("ADAPTER_REVISION = 1\n")
    invocations = []
    monkeypatch.setattr(mod, "_refresh_dependency_modules", lambda: invocations.append("sync"))
    old_fingerprint = mod.DEPENDENCY_SOURCE_SHA256
    mod.LAST_DEPENDENCY_CHECK = 0
    assert mod._refresh_worker_python() is True
    assert invocations == ["sync"]
    assert mod.LIVE_RELOAD_STATE == "AUTO_RELOADED"
    assert mod.DEPENDENCY_SOURCE_SHA256 != old_fingerprint
    assert mod.DEPENDENCY_SOURCE_SHA256 == mod._dependency_fingerprint()
    assert mod.WORKER_SOURCE_SHA256 == hashlib.sha256(source.read_bytes()).hexdigest()


def test_changed_adapter_is_not_loaded_during_running_native_job(worker, monkeypatch):
    mod, source, _state = worker
    dependency = source.parents[2] / "packages/studio/motion_adapter.py"
    dependency.parent.mkdir(parents=True)
    dependency.write_text("MOTION = 2\n")
    invocations = []
    monkeypatch.setattr(mod, "_refresh_dependency_modules", lambda: invocations.append("sync"))
    mod.BUSY = True
    mod.LAST_DEPENDENCY_CHECK = 0
    assert mod._refresh_worker_python() is True
    assert mod.LIVE_RELOAD_STATE == "DEFERRED_NATIVE_JOB"
    assert invocations == []
    assert mod.DEPENDENCY_SOURCE_SHA256 != mod._dependency_fingerprint()


def test_broken_dependency_refresh_blocks_engine_queue(worker, monkeypatch):
    mod, source, _state = worker
    dependency = source.parents[2] / "packages/studio/broken_adapter.py"
    dependency.parent.mkdir(parents=True)
    dependency.write_text("BROKEN = True\n")
    old_fingerprint = mod.DEPENDENCY_SOURCE_SHA256

    def raises():
        raise ImportError("not safe to reload")

    monkeypatch.setattr(mod, "_refresh_dependency_modules", raises)
    mod.LAST_DEPENDENCY_CHECK = 0
    assert mod._refresh_worker_python() is True
    assert mod.LIVE_RELOAD_STATE == "BLOCKED"
    assert "not safe to reload" in mod.LIVE_RELOAD_ERROR
    assert mod.DEPENDENCY_SOURCE_SHA256 == old_fingerprint
    assert mod.WORKER_SOURCE_SHA256 == hashlib.sha256(source.read_bytes()).hexdigest()
