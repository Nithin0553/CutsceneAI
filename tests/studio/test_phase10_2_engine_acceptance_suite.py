"""The seven-area engine contract cannot turn file hashes into real-engine proof."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"packages"/"studio"))

import phase10_2_engine_acceptance_suite as suite
from test_engine_acceptance_matrix import _manifest


def _bundle(workspace):
    blocks=[]
    for ident,requirements in suite.REQUIREMENTS.items():
        artifacts={}
        for name in requirements:
            path=workspace/"native"/ident/(name+".json")
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(
                json.dumps({"scope":ident,"measurement":name,"synthetic":True}),
                encoding="utf-8",
            )
            artifacts[name]={
                "path":str(path.relative_to(workspace)),
                "sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        blocks.append({"work_area_id":ident,"native_evidence":artifacts})
    return {
        "kind":suite.KIND,"schema_version":"1",
        "baseline_engine_acceptance_matrix":_manifest(workspace),
        "workstreams":blocks,
    }


def test_seven_area_complete_evidence_bundle_never_claims_engine_parity(tmp_path):
    manifest=_bundle(tmp_path)
    answer=suite.evaluate(manifest,tmp_path)
    assert answer["workstream_count"]==7
    assert len(answer["workstreams"])==7
    assert answer["status"]==(
        "ALL_EVIDENCE_HASHES_PRESENT_INDEPENDENT_ENGINE_REVIEW_REQUIRED"
    )
    assert answer["acceptance_complete"] is False
    assert answer["real_editor_execution_attested_by_this_tool"] is False


def test_missing_workstream_or_native_audio_evidence_cannot_be_omitted(tmp_path):
    manifest=_bundle(tmp_path)
    manifest["workstreams"].pop()
    with pytest.raises(suite.Phase10_2EngineAcceptanceError,match="seven"):
        suite.evaluate(manifest,tmp_path)
    manifest=_bundle(tmp_path)
    manifest["workstreams"][5]["native_evidence"].pop("native_audio_events_physics")
    with pytest.raises(suite.Phase10_2EngineAcceptanceError,match="accounted"):
        suite.evaluate(manifest,tmp_path)


def test_scenario_reordering_and_native_evidence_tampering_rejected(tmp_path):
    manifest=_bundle(tmp_path)
    manifest["workstreams"].reverse()
    with pytest.raises(suite.Phase10_2EngineAcceptanceError,match="original order"):
        suite.evaluate(manifest,tmp_path)
    manifest=_bundle(tmp_path)
    path=tmp_path/manifest["workstreams"][0]["native_evidence"][
        "rendered_camera_comparison"]["path"]
    path.write_text('{"synthesized":"changed"}',encoding="utf-8")
    with pytest.raises(suite.Phase10_2EngineAcceptanceError,match="stale"):
        suite.evaluate(manifest,tmp_path)


def test_foreign_heldout_source_identity_still_refused(tmp_path):
    manifest=_bundle(tmp_path)
    baseline=manifest["baseline_engine_acceptance_matrix"]
    held=next(row for row in baseline["cases"]
              if row["scenario"]=="HELD_OUT_SOURCE_PROJECT")
    comp=tmp_path/held["evidence_path"]
    folder=comp.parent
    target=json.loads((folder/"target-behavior.json").read_text())
    plan=json.loads((folder/"sampling-plan.json").read_text())
    target["source"]["project_fingerprint"]="unity-dev"
    plan["source"]["project_fingerprint"]="unity-dev"
    for name,object_ in (("target-behavior.json",target),
                         ("sampling-plan.json",plan)):
        (folder/name).write_text(json.dumps(object_),encoding="utf-8")
    comparison=json.loads(comp.read_text())
    comparison["target_observation_sha256"]=hashlib.sha256(
        (folder/"target-behavior.json").read_bytes()).hexdigest()
    comparison["sampling_plan_sha256"]=hashlib.sha256(
        (folder/"sampling-plan.json").read_bytes()).hexdigest()
    comp.write_text(json.dumps(comparison),encoding="utf-8")
    held["evidence_sha256"]=hashlib.sha256(comp.read_bytes()).hexdigest()
    with pytest.raises(suite.Phase10_2EngineAcceptanceError,match="Baseline"):
        suite.evaluate(manifest,tmp_path)
