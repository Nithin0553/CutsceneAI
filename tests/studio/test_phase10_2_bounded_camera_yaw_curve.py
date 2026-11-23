"""Phase 10.2: counted 2–8 measured yaw-key curve repair software contracts."""
from __future__ import annotations

import copy
import math
import sys
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[2]
for folder in ("packages/studio","integrations/unreal","tests/studio"):
    path=str(ROOT/folder)
    if path not in sys.path:
        sys.path.insert(0,path)

import agent_intent_router as router
import studio_camera_key_evidence as proof
import studio_camera_key_repair as native
from test_animated_camera_key_repair import (
    API,
    FakeSection,
    _yaw_native_job,
    _yaw_scenario,
)


def _yaw_many():
    source,target,cam,label,action,plan,csir=_yaw_scenario()
    # The previous single-key outlier is restored, then two nonadjacent
    # independently measured yaw-only outliers are introduced.
    def q(deg):
        half=math.radians(deg)/2.
        return [0.,math.sin(half),0.,math.cos(half)]
    for frame,delta in ((1,12.),(2,0.),(3,14.)):
        target["samples"][frame]["entities"][0]["world_transform"][
            "rotation_xyzw"]=q(frame*10.+delta)
    evidence=proof._analyze_grid(
        source,target,cam,label,action,plan,csir,yaw_key=True,yaw_many=True,
    )
    section=FakeSection(action,diff=0)
    for row in evidence["source_yaw_key_repairs"]:
        key=section.channels[5].keys[row["source_key_frame"]]
        key.set_value(row["native_key_value_before_degrees"])
    return source,target,cam,label,action,plan,csir,section,evidence


def test_bounded_yaw_curve_source_measurements_and_exact_count_consent():
    *_,section,evidence=_yaw_many()
    assert evidence["source_key_count"]==2
    assert [r["source_key_frame"] for r in evidence[
        "source_yaw_key_repairs"]]==[1,3]
    assert proof.requested_many_yaw_count(
        "Fix two animated camera yaw keyframes") == 2
    assert proof.requested_many_yaw_count(
        "Repair three animated CineCamera yaw keyframes") == 3
    for text in (
        "Fix animated camera yaw keyframe",
        "Fix all animated camera yaw keyframes",
        "Fix multiple animated camera yaw keyframes",
        "Fix two animated camera pitch keyframes",
        "Fix two animated camera yaw keyframes and lens",
        "Never fix two animated camera yaw keyframes",
        "Fix nine animated camera yaw keyframes",
        "Fix two animated camera yaw keyframes in a rig",
    ):
        assert proof.requested_many_yaw_count(text) is None,text
    eligible={
        **evidence,"kind":proof.KIND_MANY_YAW,"eligible":True,
        "native_edit_authorized":False,
        "animated_camera_many_yaw_repair_sha256":"f"*64,
    }
    def route(msg,known=eligible):
        return router.route(
            msg,generation_complete=True,
            native_material_fallback_slots=0,source_albedo_provenance=False,
            completed_repairs=0,repair_budget=2,independent_issues=[],
            animated_camera_many_yaw_evidence=known,
        )
    assert route("Fix two animated camera yaw keyframes")["safe_strategies"]==[
        "report_only",proof.STRATEGY_MANY_YAW,
    ]
    assert route("Fix three animated camera yaw keyframes")[
        "safe_strategies"]==["report_only"]
    assert route("Fix two animated camera yaw keyframes",{
        **eligible,"animated_camera_many_yaw_repair_sha256":"bad",
    })["safe_strategies"]==["report_only"]
    (first,one),(second,two)=native._read_many_channels(
        API,section,_yaw_many()[4],repairs=evidence[
            "source_yaw_key_repairs"],yaw_only=True,
    )
    assert (first.frame,second.frame)==(1,3)
    assert (one,two)==pytest.approx(tuple(
        r["native_key_value_before_degrees"]
        for r in evidence["source_yaw_key_repairs"]
    ))


def test_bounded_yaw_curve_rejects_adjacent_or_competing_pitch_and_position():
    source,target,cam,label,action,plan,csir,section,review=_yaw_many()
    def q(deg):
        half=math.radians(deg)/2.
        return [0.,math.sin(half),0.,math.cos(half)]
    adjacent=copy.deepcopy(target)
    adjacent["samples"][3]["entities"][0]["world_transform"][
        "rotation_xyzw"]=q(30.)
    adjacent["samples"][2]["entities"][0]["world_transform"][
        "rotation_xyzw"]=q(32.)
    with pytest.raises(proof.AnimatedCameraKeyError,match="nonadjacent"):
        proof._analyze_grid(
            source,adjacent,cam,label,action,plan,csir,yaw_key=True,yaw_many=True,
        )
    native_bad=copy.deepcopy(section)
    native_bad.channels[3].keys[0].set_value(19.)
    with pytest.raises(native.AnimatedCameraNativeError):
        native._read_many_channels(
            API,native_bad,action,repairs=review["source_yaw_key_repairs"],
            yaw_only=True,
        )


def _native_multi_job(monkeypatch,tmp_path,section,review):
    api,job,request=_yaw_native_job(monkeypatch,tmp_path,section,review)
    expected={
        **review,"kind":proof.KIND_MANY_YAW,
        "eligible":True,"source_camera_name":"CAM",
        "target_actor_label":"CameraUE",
        "source_camera_occurrence_id":"occurrence:1",
        "source_camera_action_sha256":native.position._hash(_yaw_many()[4]),
        "animated_camera_many_yaw_repair_sha256":"a"*64,
    }
    monkeypatch.setattr(native.evidence,"build_many_yaw_keys",lambda *a:expected)
    previous_load=native._load
    def read(path):
        item=previous_load(path)
        if "user-feedback-" in str(path) and "active" not in str(path):
            item=dict(item,message="Fix two animated camera yaw keyframes")
        return item
    monkeypatch.setattr(native,"_load",read)
    request.update({
        "strategy":proof.STRATEGY_MANY_YAW,
        "animated_camera_many_yaw_repair_sha256":"a"*64,
    })
    return api,job,request


def test_bounded_yaw_curve_native_full_grid_save_and_rollback(monkeypatch,tmp_path):
    *_,section,review=_yaw_many()
    action=_yaw_many()[4]
    api,job,request=_native_multi_job(monkeypatch,tmp_path,section,review)
    receipt=native.attempt_many_yaw(api,tmp_path,job,request)
    assert receipt["status"]==(
        "BOUNDED_ANIMATED_CAMERA_YAW_KEYS_SAVED_REOPENED_CINETWIN_PENDING"
    )
    assert receipt["changes"]==2
    assert receipt["source_key_frames"]==[1,3]
    assert receipt["native_yaw_max_difference_after_degrees"]==0
    assert receipt["cinetwin_reopened_after_repair_verified"] is False
    native._all_camera_keys_match_source(API,section,action)
    *_,failing,review=_yaw_many()
    api,job,request=_native_multi_job(monkeypatch,tmp_path,failing,review)
    api.EditorAssetLibrary.save_loaded_asset=lambda seq:False
    with pytest.raises(native.AnimatedCameraNativeError,match="save"):
        native.attempt_many_yaw(api,tmp_path,job,request)
    assert failing.channels[5].keys[1].get_value()==pytest.approx(
        review["source_yaw_key_repairs"][0]["native_key_value_before_degrees"]
    )
    assert failing.channels[5].keys[3].get_value()==pytest.approx(
        review["source_yaw_key_repairs"][1]["native_key_value_before_degrees"]
    )


def test_bounded_yaw_curve_rollback_after_second_key_mutates_then_throws(
        monkeypatch,tmp_path):
    *_,section,review=_yaw_many()
    second=section.channels[5].keys[3]
    previous=second.set_value
    def setter(value):
        previous(value)
        if abs(float(value)-review["source_yaw_key_repairs"][1][
                "source_key_value_degrees"])<0.0001:
            raise RuntimeError("Second yaw key mutated then threw")
    second.set_value=setter
    api,job,request=_native_multi_job(monkeypatch,tmp_path,section,review)
    with pytest.raises(RuntimeError,match="mutated then threw"):
        native.attempt_many_yaw(api,tmp_path,job,request)
    assert section.channels[5].keys[1].get_value()==pytest.approx(
        review["source_yaw_key_repairs"][0]["native_key_value_before_degrees"]
    )
    assert section.channels[5].keys[3].get_value()==pytest.approx(
        review["source_yaw_key_repairs"][1]["native_key_value_before_degrees"]
    )
