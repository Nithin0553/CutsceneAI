"""Phase 10.5 localhost startup smoke must be isolated and fail closed.

Real-process execution from an extracted ZIP runs separately on Windows CI.
These unit tests cover report/auth semantics without launching a model/editor.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"tools"))
import studio_startup_smoke as smoke


def _source(tmp_path):
    root=tmp_path/"studio"
    (root/"tools").mkdir(parents=True)
    (root/"apps/studio-web").mkdir(parents=True)
    (root/"tools/studio_local_bridge.py").write_text("# fake server",encoding="utf-8")
    (root/"apps/studio-web/index.html").write_text("<title>CutSceneAI Studio</title>",encoding="utf-8")
    return root


class FakeProcess:
    def __init__(self):
        self.stopped=False
    def poll(self):
        return 0 if self.stopped else None
    def terminate(self):
        self.stopped=True
    def wait(self,timeout=None):
        self.stopped=True
        return 0
    def kill(self):
        self.stopped=True


def _mock(tmp_path,monkeypatch,*,connected=False,post_code=403):
    root=_source(tmp_path)
    process=FakeProcess()
    def spawn(args,**kwargs):
        assert args[1]==str(root/"tools/studio_local_bridge.py")
        assert "--workspace" in args
        assert kwargs["env"]["CUTSCENEAI_MODEL_PROVIDER"]=="ollama"
        assert kwargs["stdin"]==smoke.subprocess.DEVNULL
        return process
    monkeypatch.setattr(smoke.subprocess,"Popen",spawn)
    calls=[]
    def fake_fetch(url,*,method="GET",headers=None,body=None):
        calls.append((url,method,headers or {}))
        if method=="POST":
            assert body==b"{}"
            return post_code,b'{"error":"Local session token required."}'
        if headers and headers.get("Host")=="untrusted.example":
            return 403,b'{"error":"Local origin required."}'
        if url.endswith("/api/status"):
            return 200,json.dumps({"connected":connected,"token":"x"*32}).encode()
        if url.endswith("/api/release-readiness"):
            return 200,b'{"release_ready":false}'
        if url.endswith("/api/flow-diagnostics"):
            return 200,b'{"native_replay_authorized":false,"source_and_native_full_fidelity_verified":false}'
        if url.endswith("/cinematic.js"):
            return 200,b"/"*3000
        if url.endswith("/"):
            return 200,b"<title>CutSceneAI Studio</title>"
        raise AssertionError("Unexpected smoke route "+url)
    monkeypatch.setattr(smoke,"_fetch",fake_fetch)
    return root,process,calls


def test_startup_smoke_proves_http_protection_and_does_not_start_engines(
        tmp_path,monkeypatch):
    root,process,calls=_mock(tmp_path,monkeypatch)
    receipt=smoke.run(root,timeout_seconds=3)
    assert receipt["status"]=="LIVE_LOCALHOST_AND_UI_SMOKE_PASSED_ENGINE_UNVERIFIED"
    assert receipt["production_release_ready"] is False
    assert receipt["native_editor_started"] is False
    assert receipt["unity_editor_started"] is False
    assert receipt["model_invoked"] is False
    assert process.stopped is True
    assert len(receipt["checks"])==8
    assert any(path.endswith("/api/connect") for path,_,_ in calls)


def test_startup_smoke_rejects_forged_editor_source_connection(
        tmp_path,monkeypatch):
    root,process,_=_mock(tmp_path,monkeypatch,connected=True)
    with pytest.raises(smoke.SmokeError,match="falsely has a source"):
        smoke.run(root,timeout_seconds=3)
    assert process.stopped


def test_startup_smoke_rejects_public_mutation_without_session_token(
        tmp_path,monkeypatch):
    root,process,_=_mock(tmp_path,monkeypatch,post_code=200)
    with pytest.raises(smoke.SmokeError,match="session token"):
        smoke.run(root,timeout_seconds=3)
    assert process.stopped


def test_startup_smoke_requires_full_distribution_and_bounded_timeout(
        tmp_path):
    with pytest.raises(smoke.SmokeError,match="complete"):
        smoke.run(tmp_path)
    root=_source(tmp_path)
    with pytest.raises(smoke.SmokeError,match="between 2 and 120"):
        smoke.run(root,timeout_seconds=0)
