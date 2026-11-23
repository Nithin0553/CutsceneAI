"""Phase 10.5 pre-engine software handoff must fail closed on any mismatch."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"tools"))
import phase10_5_freeze_preflight as freeze

SHA="a"*40


def _ready(tmp_path,monkeypatch):
    root=tmp_path/"checkout"
    root.mkdir()
    zip_path=tmp_path/"source.zip"
    zip_path.write_bytes(b"source-only ZIP verification is mocked here")
    receipt=tmp_path/"rehearsal.json"
    matrix={"kind":"cutsceneai.studio.phase10_4.matrix",
            "total_gates":19,"source_sha256":{"cases":"b"*64}}
    plan={"kind":"cutsceneai.studio.phase10_4.synthetic_rehearsal_plan",
          "exact_scenario_matrix":matrix}
    proof={
        "kind":"cutsceneai.studio.phase10_4.synthetic_rehearsal",
        "status":"SYNTHETIC_REHEARSAL_PASSED_ENGINE_ACCEPTANCE_PENDING",
        "exact_matrix_all_gates_exercised":True,
        "native_replay_authorized":False,
        "release_candidate_ready":False,
        "post_reopen_fidelity_verified":False,
        "unreal_editor_executed":False,
        "unity_editor_executed":False,
        "plan":plan,
        "runs":[
            {"command_category":"python_synthetic_regressions",
             "exit_code":0,"test_summary":"200 passed","stdout_sha256":"c"*64},
            {"command_category":"node_ui_interruption_regressions",
             "exit_code":0,"test_summary":"26 scenarios","stdout_sha256":"d"*64},
        ],
    }
    receipt.write_text(json.dumps(proof),encoding="utf-8")
    monkeypatch.setattr(freeze.bundle,"verify_exact_checkout",lambda _root,_archive: {
        "status":"SOURCE_BUNDLE_HASHES_VERIFIED_ENGINE_PENDING",
        "sha256":"e"*64,"file_count":600,"exact_checked_out_source_verified":True,
    })
    monkeypatch.setattr(freeze.rehearsal,"plan",lambda _:plan)
    monkeypatch.setattr(freeze.matrix,"verify",lambda _:matrix)
    return root,zip_path,receipt,proof


def test_10_5_exact_head_and_verified_rehearsal_authorize_only_pre_engine_handoff(
        tmp_path,monkeypatch):
    root,zip_path,receipt,_=_ready(tmp_path,monkeypatch)
    report=freeze.assess(
        root,bundle_path=zip_path,rehearsal_path=receipt,
        expected_sha=SHA,head_reader=lambda _:SHA,
    )
    assert report["status"]=="PRE_ENGINE_SOFTWARE_HANDOFF_READY"
    assert report["software_checks"]["phase10_4_scenario_count"]==19
    assert report["software_checks"]["exact_commit_and_clean_tracked_tree"]=="PASS"
    assert report["production_release_ready"] is False
    assert report["final_freeze_authorized"] is False
    assert report["engine_fidelity_verified"] is False
    assert report["native_replay_authorized"] is False
    assert all(x=="INCOMPLETE" for x in report["real_engine_acceptance"].values())


def test_10_5_refuses_sha_mismatch_and_non_commit_identifier(tmp_path,monkeypatch):
    root,zip_path,receipt,_=_ready(tmp_path,monkeypatch)
    with pytest.raises(freeze.FreezeError,match="independently observed"):
        freeze.assess(root,bundle_path=zip_path,rehearsal_path=receipt,
                      expected_sha=SHA,head_reader=lambda _:"b"*40)
    with pytest.raises(freeze.FreezeError,match="40-character"):
        freeze.assess(root,bundle_path=zip_path,rehearsal_path=receipt,
                      expected_sha="feature/latest",head_reader=lambda _:SHA)


@pytest.mark.parametrize("change",[
    {"status":"SYNTHETIC_REHEARSAL_FAILED"},
    {"exact_matrix_all_gates_exercised":False},
    {"native_replay_authorized":True},
    {"release_candidate_ready":True},
    {"unreal_editor_executed":True},
    {"post_reopen_fidelity_verified":True},
    {"runs":[{"command_category":"python_synthetic_regressions",
              "exit_code":0,"test_summary":"200 passed","stdout_sha256":"b"*64}]},
])
def test_10_5_refuses_unproven_or_fake_engine_proofs(
        tmp_path,monkeypatch,change):
    root,zip_path,receipt,proof=_ready(tmp_path,monkeypatch)
    proof.update(change)
    receipt.write_text(json.dumps(proof),encoding="utf-8")
    with pytest.raises(freeze.FreezeError):
        freeze.assess(root,bundle_path=zip_path,rehearsal_path=receipt,
                      expected_sha=SHA,head_reader=lambda _:SHA)


def test_10_5_refuses_stale_suite_hashes(tmp_path,monkeypatch):
    root,zip_path,receipt,proof=_ready(tmp_path,monkeypatch)
    proof["plan"]["exact_scenario_matrix"]["source_sha256"]["cases"]="f"*64
    receipt.write_text(json.dumps(proof),encoding="utf-8")
    # Independent source matrix now disagrees with the serialized receipt.
    monkeypatch.setattr(freeze.matrix,"verify",lambda _: {
        "kind":"cutsceneai.studio.phase10_4.matrix",
        "total_gates":19,"source_sha256":{"cases":"b"*64},
    })
    monkeypatch.setattr(freeze.rehearsal,"plan",lambda _: {
        "kind":"cutsceneai.studio.phase10_4.synthetic_rehearsal_plan",
        "exact_scenario_matrix":{
            "kind":"cutsceneai.studio.phase10_4.matrix",
            "total_gates":19,"source_sha256":{"cases":"b"*64},
        },
    })
    with pytest.raises(freeze.FreezeError,match="source bytes differ"):
        freeze.assess(root,bundle_path=zip_path,rehearsal_path=receipt,
                      expected_sha=SHA,head_reader=lambda _:SHA)


def test_10_5_refuses_invalid_bundle_verification(tmp_path,monkeypatch):
    root,zip_path,receipt,_=_ready(tmp_path,monkeypatch)
    monkeypatch.setattr(freeze.bundle,"verify_exact_checkout",lambda _root,_archive: {
        "status":"SOURCE_BUNDLE_HASHES_FAILED",
    })
    with pytest.raises(freeze.FreezeError,match="Distribution source"):
        freeze.assess(root,bundle_path=zip_path,rehearsal_path=receipt,
                      expected_sha=SHA,head_reader=lambda _:SHA)
