"""Phase 10.5 cross-platform source ZIP/Windows host handoff is fail closed."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"tools"))
import phase10_5_package_acceptance as contract

SHA="a"*40


def _fixture(tmp_path):
    bundle=tmp_path/"studio.zip"
    bundle.write_bytes(b"nonempty verified source bytes")
    checks={
        "exact_commit_and_clean_tracked_tree":"PASS",
        "phase10_4_all_software_gates":"PASS",
        "source_bundle_sha256_verified":"PASS",
        "native_replay_contract":"PASS_NO_REPLAY",
        "phase10_4_scenario_count":19,
        "source_bundle_sha256":hashlib.sha256(bundle.read_bytes()).hexdigest(),
        "source_manifest_sha256":"c"*64,
    }
    preflight={
        "kind":"cutsceneai.studio.phase10_5.pre_engine_freeze_preflight",
        "source_git_sha":SHA,
        "status":"PRE_ENGINE_SOFTWARE_HANDOFF_READY",
        "software_checks":checks,
        "production_release_ready":False,
        "final_freeze_authorized":False,
        "engine_fidelity_verified":False,
    }
    smoke={
        "kind":"cutsceneai.studio.phase10_5.localhost_startup_smoke",
        "status":"LIVE_LOCALHOST_AND_UI_SMOKE_PASSED_ENGINE_UNVERIFIED",
        "source_distribution_sha256":hashlib.sha256(bundle.read_bytes()).hexdigest(),
        "source_manifest_sha256":"c"*64,
        "checks":{item:"PASS" for item in contract.STARTUP_CHECKS},
        "native_editor_started":False,"unity_editor_started":False,
        "model_invoked":False,"full_cutscene_fidelity_verified":False,
        "production_release_ready":False,
    }
    rehearsal={
        "kind":"cutsceneai.studio.phase10_4.synthetic_rehearsal",
        "status":"SYNTHETIC_REHEARSAL_PASSED_ENGINE_ACCEPTANCE_PENDING",
        "scenario_gate_count":19,"exact_matrix_all_gates_exercised":True,
        "release_candidate_ready":False,"native_replay_authorized":False,
    }
    docs=[]
    for name,content in (("preflight",preflight),("startup",smoke),("rehearsal",rehearsal)):
        path=tmp_path/(name+".json")
        path.write_text(json.dumps(content),encoding="utf-8")
        docs.append(path)
    return bundle,docs,preflight,smoke,rehearsal


def _check(bundle,docs,commit=SHA):
    return contract.assess(
        commit=commit,bundle=bundle,preflight=docs[0],
        startup=docs[1],rehearsal=docs[2],
    )


def test_windows_real_server_and_source_zip_require_same_reviewed_commit(tmp_path):
    bundle,docs,*_=_fixture(tmp_path)
    record=_check(bundle,docs)
    assert record["status"]=="SOFTWARE_PACKAGE_READY_FOR_ENGINE_TEST"
    assert record["source_git_sha"]==SHA
    assert record["verified"]["phase10_4_source_only_gates"]==19
    assert record["verified"]["windows_clean_source_zip_installed"] is True
    assert record["verified"]["actual_packaged_studio_localhost_started"] is True
    assert record["native_replay_authorized"] is False
    assert record["real_engine_acceptance_complete"] is False
    assert record["final_release_frozen"] is False
    assert record["production_release_ready"] is False


@pytest.mark.parametrize("field,value",[
    ("status","SYNTHETIC_REHEARSAL_FAILED"),
    ("scenario_gate_count",18),
    ("exact_matrix_all_gates_exercised",False),
    ("native_replay_authorized",True),
    ("release_candidate_ready",True),
])
def test_missing_or_overclaiming_10_4_evidence_blocks_distribution(
        tmp_path,field,value):
    bundle,docs,_,_,rehearsal=_fixture(tmp_path)
    rehearsal[field]=value
    docs[2].write_text(json.dumps(rehearsal),encoding="utf-8")
    with pytest.raises(contract.PackageAcceptanceError,match="rehearsal"):
        _check(bundle,docs)


@pytest.mark.parametrize("field,value",[
    ("status","FAILED"),
    ("native_editor_started",True),
    ("full_cutscene_fidelity_verified",True),
    ("production_release_ready",True),
])
def test_failed_or_forged_windows_startup_is_not_ready(tmp_path,field,value):
    bundle,docs,_,smoke,_=_fixture(tmp_path)
    smoke[field]=value
    docs[1].write_text(json.dumps(smoke),encoding="utf-8")
    with pytest.raises(contract.PackageAcceptanceError,match="startup|start Studio|Windows smoke|falsely"):
        _check(bundle,docs)


def test_missing_auth_protection_or_smoke_gate_blocks_handoff(tmp_path):
    bundle,docs,_,smoke,_=_fixture(tmp_path)
    smoke["checks"].pop("session_token_required")
    docs[1].write_text(json.dumps(smoke),encoding="utf-8")
    with pytest.raises(contract.PackageAcceptanceError,match="startup checks"):
        _check(bundle,docs)


def test_zip_tampering_and_wrong_sha_block_handoff(tmp_path):
    bundle,docs,*_=_fixture(tmp_path)
    bundle.write_bytes(b"altered ZIP bytes after freeze")
    with pytest.raises(contract.PackageAcceptanceError,match="ZIP bytes"):
        _check(bundle,docs)
    with pytest.raises(contract.PackageAcceptanceError,match="40-character"):
        _check(bundle,docs,commit="branch-name")


def test_mismatched_handoff_commit_is_rejected(tmp_path):
    bundle,docs,preflight,*_=_fixture(tmp_path)
    preflight["source_git_sha"]="b"*40
    docs[0].write_text(json.dumps(preflight),encoding="utf-8")
    with pytest.raises(contract.PackageAcceptanceError,match="another commit"):
        _check(bundle,docs)


def test_packaged_windows_source_zip_different_from_linux_is_rejected(tmp_path):
    bundle,docs,_,smoke,_=_fixture(tmp_path)
    smoke["source_manifest_sha256"]="f"*64
    docs[1].write_text(json.dumps(smoke),encoding="utf-8")
    with pytest.raises(contract.PackageAcceptanceError,match="source manifest differs"):
        _check(bundle,docs)
