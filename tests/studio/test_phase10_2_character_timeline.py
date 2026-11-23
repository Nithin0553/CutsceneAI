"""Synthetic Phase 10.2 contracts for multi-character/hierarchy and Timeline.

These tests demonstrate deterministic source-evidence refusal only; no
Unity/Unreal Editor is launched and no native retargeting is claimed.
"""
from __future__ import annotations

import copy
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "studio"))
sys.path.insert(0, str(ROOT / "integrations" / "unreal"))
import character_motion
import multi_character_sync as sync
import timeline_blend_policy as timeline

RATE = {"numerator": 2,"denominator":1}


def _time(seconds):
    return {"value":seconds*2,"rate":RATE}


def _sample(t):
    return {
        "time_seconds":t,
        "entities":[
            {"entity_id":"a","actor_label":"Actor_A",
             "world_transform":{
                 "position_m":[t,0.,0.],
                 "rotation_xyzw":[0.,0.,0.,1.],
                 "scale_xyz":[1.,1.,1.],
             }},
            {"entity_id":"b","actor_label":"Actor_B",
             "world_transform":{
                 "position_m":[t+2.,0.,0.],
                 "rotation_xyzw":[0.,0.,0.,1.],
                 "scale_xyz":[1.,1.,1.],
             }},
        ],
    }


def _scene():
    csir = {
        "timing":{
            "source_rate":RATE,"display_rate":RATE,
            "playback_start":_time(0),"playback_end":_time(2),
            "duration_seconds":2.,
        },
        "entities":[
            {"entity_id":"a","name":"Alice","ced_type":"entity.character"},
            {"entity_id":"b","name":"Bob","ced_type":"entity.character"},
        ],
        "tracks":[],
    }
    capture={"samples":[_sample(i/2.) for i in range(5)]}
    mapping={"entities":{
        "Alice":{"actor_label":"Actor_A"},"Bob":{"actor_label":"Actor_B"},
    }}
    return csir,capture,mapping


def test_multi_character_complete_common_grid_and_pairwise_spacing():
    csir,source,mapping=_scene()
    report=sync.analyze(csir,source,mapping=mapping,target=source)
    assert report["source_character_count"]==2
    assert report["shared_frame_count"]==5
    assert len(report["source_pair_distances"])==1
    assert report["source_pair_distances"][0]["minimum_source_separation_m"]==2.
    assert report["native_source_binding_checked"] is True
    assert report["independently_reopened_native_cinetwin_verified"] is False
    assert report["native_animation_or_retarget_execution_authorized"] is False
    assert all(r["actor_world_comparison_within_tolerance"] is True
               for r in report["per_character"])
    assert all(r["native_bone_pose_verified"] is False
               for r in report["per_character"])


def test_multi_character_native_drift_is_measured_never_auto_repaired():
    csir,source,mapping=_scene()
    target=copy.deepcopy(source)
    target["samples"][2]["entities"][1]["world_transform"]["position_m"][0]+=0.5
    report=sync.analyze(csir,source,mapping=mapping,target=target)
    b=next(r for r in report["per_character"] if r["source_entity_id"]=="b")
    assert b["maximum_actor_world_drift_cm"] == pytest.approx(50.)
    assert b["actor_world_comparison_within_tolerance"] is False
    assert report["native_animation_or_retarget_execution_authorized"] is False


@pytest.mark.parametrize("mutate,part",[
    (lambda csir,capture,mapping: capture["samples"].pop(1),"complete original"),
    (lambda csir,capture,mapping: capture["samples"].append(
        copy.deepcopy(capture["samples"][2])),"complete original"),
    (lambda csir,capture,mapping: capture["samples"][1]["entities"].pop(0),
     "complete original"),
    (lambda csir,capture,mapping: capture["samples"][0]["entities"][0][
        "world_transform"].__setitem__("rotation_xyzw",[0,0,0,0]),"complete original"),
    (lambda csir,capture,mapping: csir["entities"][1].__setitem__(
        "entity_id","a"),"Duplicate"),
    (lambda csir,capture,mapping: csir["entities"][0].__setitem__(
        "parent_entity_id","b") or csir["entities"][1].__setitem__(
        "parent_entity_id","a"),"cycle"),
    (lambda csir,capture,mapping: csir["entities"][0].__setitem__(
        "parent_entity_id","absent"),"Unresolved"),
    (lambda csir,capture,mapping: mapping["entities"]["Bob"].__setitem__(
        "actor_label","Actor_A"),"ambiguous"),
])
def test_multi_character_refuses_missing_sample_identity_or_parent(mutate,part):
    csir,capture,mapping=_scene()
    mutate(csir,capture,mapping)
    with pytest.raises(sync.CharacterSyncError,match=part):
        sync.analyze(csir,capture,mapping=mapping)


def test_multi_character_refuses_native_binding_swap_and_bad_quaternion():
    csir,source,mapping=_scene()
    target=copy.deepcopy(source)
    target["samples"][0]["entities"][0]["actor_label"]="Actor_B"
    with pytest.raises(sync.CharacterSyncError,match="source mapped"):
        sync.analyze(csir,source,mapping=mapping,target=target)
    target=copy.deepcopy(source)
    target["samples"][2]["entities"][1]["world_transform"]["rotation_xyzw"]=[
        math.nan,0.,0.,1.,
    ]
    with pytest.raises(character_motion.MotionError):
        sync.analyze(csir,source,mapping=mapping,target=target)


def test_character_root_relative_pose_rejects_truncated_vectors_and_nonunit_rotation():
    actor={"position_m":[1.,0.,0.],"rotation_xyzw":[0.,0.,0.,1.]}
    root={"position_m":[2.,0.,0.],"rotation_xyzw":[0.,0.,0.,1.]}
    position,rotation=character_motion.relative_root(actor,root)
    assert position==pytest.approx([1.,0.,0.])
    assert rotation==pytest.approx([0.,0.,0.,1.])
    for invalid in (
        {"position_m":[2.,0.],"rotation_xyzw":[0.,0.,0.,1.]},
        {"position_m":[2.,math.nan,0.],"rotation_xyzw":[0.,0.,0.,1.]},
        {"position_m":[2.,0.,0.],"rotation_xyzw":[0.,0.,0.,0.]},
        {"position_m":[2.,0.,0.],"rotation_xyzw":None},
    ):
        with pytest.raises(character_motion.MotionError):
            character_motion.relative_root(actor,invalid)


def _complex_scene():
    csir,_source,mapping=_scene()
    csir["tracks"]=[
        {"ced_type":"camera.cut","track_id":"cuts","sections":[
            {"start":_time(0),"end":_time(1)},
            {"start":_time(1),"end":_time(2)},
        ]},
        {"ced_type":"camera.transform","track_id":"cam",
         "binding_entity_id":"c","sections":[
             {"start":_time(0),"end":_time(2),
              "native_payload":{"blend_in_seconds":0.2}},
         ]},
        {"ced_type":"cinematic.shot","track_id":"nested","sections":[
            {"start":_time(0),"end":_time(2)},
        ]},
    ]
    csir["entities"].append({
        "entity_id":"c","name":"Camera","ced_type":"entity.camera",
    })
    mapping["entities"]["Camera"]={"actor_label":"CamActor"}
    return csir,mapping


def test_complex_timeline_census_preserves_nested_shot_and_easing_blockers():
    csir,mapping=_complex_scene()
    report=timeline.analyze_complex_timeline(csir,mapping)
    assert report["source_track_count"]==3
    assert report["camera_cut_section_count"]==2
    assert report["source_time_owners_with_blockers"]==2
    by_kind={row["source_kind"]:row for row in report["tracks"]}
    assert "SOURCE_SECTION_EASING_OR_CROSSFADE" in by_kind[
        "camera.transform"]["reason_codes"]
    assert "UNSUPPORTED_NESTED_OR_BLENDED_TIME_OWNER" in by_kind[
        "cinematic.shot"]["reason_codes"]
    assert report["native_repair_authorized"] is False
    assert report["native_subsequence_fidelity_verified"] is False


def test_complex_timeline_detects_overlapping_camera_cut_owners():
    csir,mapping=_complex_scene()
    csir["tracks"][0]["sections"][1]["start"]=_time(0.5)
    report=timeline.analyze_complex_timeline(csir,mapping)
    assert "OVERLAPPING_SOURCE_TRACK_SECTIONS" in report["tracks"][0][
        "reason_codes"]
    assert "OVERLAPPING_CAMERA_CUT_OWNERS" in report["tracks"][0][
        "reason_codes"]


def test_complex_timeline_refuses_missing_section_and_unproven_retiming():
    csir,mapping=_complex_scene()
    csir["tracks"][2]["sections"][0].pop("end")
    with pytest.raises(timeline.TimelineBlendError,match="Incomplete"):
        timeline.analyze_complex_timeline(csir,mapping)
    csir,mapping=_complex_scene()
    csir["tracks"][1]["sections"][0]["native_payload"]["time_scale_curve"]="unknown"
    report=timeline.analyze_complex_timeline(csir,mapping)
    assert "SOURCE_NESTED_OR_RETIMED_SECTION_METADATA" in report[
        "tracks"][1]["reason_codes"]
