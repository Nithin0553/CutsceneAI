"""Phase 10.3 source-safe setup and shared read-only orchestration tests."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"tools"))
sys.path.insert(0,str(ROOT/"packages"/"studio"))

import studio_companion_install as install
import studio_phase10_3_flow as flow


def _projects(tmp_path):
    repo=tmp_path/"Studio"
    pkg=repo/"integrations/unity/com.cutsceneai.extractor"
    pkg.mkdir(parents=True)
    (pkg/"package.json").write_text(json.dumps({
        "name":"com.cutsceneai.extractor","version":"0.1.5",
    }),encoding="utf-8")
    (repo/"integrations/unreal").mkdir(parents=True)
    (repo/"integrations/unreal/studio_local_editor_worker.py").write_text(
        "# worker",encoding="utf-8",
    )
    (repo/"tools").mkdir(parents=True)
    (repo/"tools/studio_local_bridge.py").write_text(
        "# localhost host",encoding="utf-8",
    )
    unity=tmp_path/"OriginalUnity"
    for part in ("Assets","ProjectSettings","Packages"):
        (unity/part).mkdir(parents=True)
    manifest=unity/"Packages/manifest.json"
    manifest.write_text(json.dumps({"dependencies":{
        "com.unity.timeline":"1.8.10",
    }}),encoding="utf-8")
    unreal=tmp_path/"TargetUnreal"
    unreal.mkdir()
    up=unreal/"Target.uproject"
    up.write_text(json.dumps({
        "FileVersion":3,
        "Plugins":[{"Name":"PythonScriptPlugin","Enabled":True}],
    }),encoding="utf-8")
    return repo,unity,up,manifest


def test_first_run_companion_dry_run_never_changes_engine_project(tmp_path):
    repo,unity,up,manifest=_projects(tmp_path)
    before=manifest.read_bytes()
    plan=install.inspect(repo,unity,up)
    assert plan["steps"]==[
        "WRITE_UNITY_LOCAL_UPM_DEPENDENCY_WITH_BACKUP",
        "CREATE_UNREAL_PROJECT_PYTHON_STARTUP_EXCLUSIVELY",
    ]
    assert manifest.read_bytes()==before
    assert not (up.parent/"Content").exists()
    assert plan["real_companion_activation_verified"] is False


def test_explicit_companion_wiring_is_non_overwriting_and_idempotent(tmp_path):
    repo,unity,up,manifest=_projects(tmp_path)
    receipt=install.install(repo,unity,up,consent=True)
    assert receipt["status"]=="PROJECT_WIRING_WRITTEN_EDITOR_ACTIVATION_UNVERIFIED"
    assert receipt["unity_backup_created"] is True
    assert (manifest.parent/"manifest.json.cutsceneai-before-install.bak").is_file()
    deps=json.loads(manifest.read_text())["dependencies"]
    assert deps["com.cutsceneai.extractor"].startswith("file:")
    startup=(up.parent/"Content/Python/init_unreal.py").read_text()
    assert "studio_local_editor_worker" in startup
    assert "if _csai_worker.HANDLE is None" in startup
    assert receipt["real_companion_activation_verified"] is False
    again=install.inspect(repo,unity,up)
    assert again["steps"]==[]
    again_receipt=install.install(repo,unity,up,consent=True)
    assert again_receipt["steps"]==[]
    assert again_receipt["unity_backup_created"] is False


def test_unreal_python_plugin_disabled_blocks_before_unity_write(tmp_path):
    repo,unity,up,manifest=_projects(tmp_path)
    up.write_text('{"Plugins":[]}',encoding="utf-8")
    before=manifest.read_bytes()
    with pytest.raises(install.CompanionInstallError,match="PythonScriptPlugin"):
        install.install(repo,unity,up,consent=True)
    assert manifest.read_bytes()==before


def test_foreign_bootstrap_and_different_unity_package_refused(tmp_path):
    repo,unity,up,manifest=_projects(tmp_path)
    startup=up.parent/"Content/Python/init_unreal.py"
    startup.parent.mkdir(parents=True)
    startup.write_text("print('user script')",encoding="utf-8")
    with pytest.raises(install.CompanionInstallError,match="not Studio-owned"):
        install.inspect(repo,unity,up)
    startup.unlink()
    manifest.write_text(json.dumps({"dependencies":{
        "com.cutsceneai.extractor":"https://different-publisher.invalid/package",
    }}))
    with pytest.raises(install.CompanionInstallError,match="Different Unity extractor"):
        install.inspect(repo,unity,up)


def test_symlinked_unity_manifest_refused_before_native_mutation(tmp_path):
    repo,unity,up,manifest=_projects(tmp_path)
    external=tmp_path/"external-manifest.json"
    external.write_bytes(manifest.read_bytes())
    manifest.unlink()
    try:
        manifest.symlink_to(external)
    except (OSError,NotImplementedError):
        pytest.skip("Filesystem denies symlinks.")
    with pytest.raises(install.CompanionInstallError,match="Symlinked|redirected"):
        install.inspect(repo,unity,up)
    assert not (up.parent/"Content").exists()


def _snapshot(job_id="",*,worker=True,unity=True):
    return {
        "active_job":job_id,
        "connection":{"source_rights_confirmed":True},
        "candidate":{"candidate_id":"candidate-a"},
        "unity_editor":{"connected":unity,"status":"CURRENT",
                        "next_action":"Open exact Unity project."},
        "unreal_worker":{"connected":worker},
        "destination_readiness":{"ready":worker,"next_action":
                                 "Inspect destination level."},
    }


def test_all_nine_stages_have_explicit_unknown_fidelity_and_no_replay():
    report=flow.summarize(
        _snapshot(),{"active":True,"status":"WAITING_FOR_UNITY_CAPTURE",
                     "candidate_id":""},
    )
    assert len(report["stages"])==9
    assert [row["id"] for row in report["stages"]]==list(range(1,10))
    assert report["native_replay_authorized"] is False
    assert report["source_and_native_full_fidelity_verified"] is False
    assert all(row["native_or_rendered_fidelity_verified"] is False
               for row in report["stages"])


def test_current_generated_job_is_not_wrongly_reported_as_full_fidelity():
    identifier="a"*32
    report=flow.summarize(
        _snapshot(identifier),
        {"active":True,"status":"GENERATED_UNVERIFIED",
         "job_id":identifier,"candidate_id":"candidate-a"},
        {"job_id":identifier,"generation_status":"GENERATED_UNVERIFIED",
         "status":"GENERATED"},
    )
    assert report["native_job_identity_matches_current_run"] is True
    assert report["stages"][5]["status"]=="GENERATED_BUT_FIDELITY_UNVERIFIED"
    assert report["native_replay_authorized"] is False
    assert report["stages"][8]["status"]=="NOT_VERIFIED"


def test_blocked_new_run_cannot_reuse_old_job_or_native_result():
    old_id="a"*32
    report=flow.summarize(
        _snapshot(old_id,worker=False),
        {"active":True,"status":"BLOCKED","job_id":"",
         "recovery_action":"Inspect source rights and create new candidate."},
        {"job_id":old_id,"generation_status":"GENERATED_UNVERIFIED"},
    )
    assert report["native_job_identity_matches_current_run"] is False
    assert report["native_status"]=="NOT_CURRENT"
    assert report["native_replay_authorized"] is False
    assert "Inspect source rights" in report["next_action"]
    assert report["stages"][5]["status"]!="GENERATED_BUT_FIDELITY_UNVERIFIED"


def test_wrong_worker_project_and_missing_source_give_actionable_diagnostics():
    report=flow.summarize(
        _snapshot(worker=False,unity=False),
        {"active":True,"status":"WAITING_FOR_UNREAL"},
    )
    assert any("Unity" in issue for issue in report["issues"])
    assert any("Unreal" in issue for issue in report["issues"])
    assert report["native_replay_authorized"] is False
