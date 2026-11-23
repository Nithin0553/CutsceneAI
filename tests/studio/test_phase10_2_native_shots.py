"""Synthetic validated nested shot native authoring and rollback tests."""
from __future__ import annotations

import copy
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"integrations"/"unreal"))

import studio_native_shot_tracks as shots


def _time(frames):
    return {"value":frames,"rate":{"numerator":24,"denominator":1}}


def _scene():
    csir={
        "cutscene_id":"measured-source","source":{"engine":"unity"},
        "timing":{
            "display_rate":{"numerator":24,"denominator":1},
            "duration_seconds":2.,
        },
        "tracks":[{
            "ced_type":"cinematic.shot","track_id":"shot-1","sections":[
                {"section_id":"s0","start":_time(0),"end":_time(20)},
                {"section_id":"s1","start":_time(20),"end":_time(48)},
            ],
        }],
    }
    approval={
        "kind":"cutsceneai.studio.approved_native_nested_shots",
        "schema_version":"1",
        "source_csir_sha256":"a"*64,
        "reviewed_native_sequence_owners":True,
        "parent_sequence_path":"/Game/Films/Root",
        "shots":[
            {"section_id":"s0","child_sequence_path":"/Game/Films/Shot_01"},
            {"section_id":"s1","child_sequence_path":"/Game/Films/Shot_02"},
        ],
    }
    return csir,approval


class FakeAsset:
    def __init__(self,path):
        self.path=path
    def get_path_name(self):
        return self.path+"."+self.path.rsplit("/",1)[1]
    def get_class(self):
        return NS(get_name=lambda:"LevelSequence")


class FakeSection:
    def __init__(self):
        self.range=None
        self.sequence=None
    def set_sequence(self,sequence):
        self.sequence=sequence
    def set_range(self,start,end):
        self.range=(start,end)
    def get_sequence(self):
        return self.sequence


class FakeTrack:
    def __init__(self):
        self.sections=[]
    def add_section(self):
        value=FakeSection()
        self.sections.append(value)
        return value
    def get_sections(self):
        return self.sections


def _api(save=True,*,corrupt=False):
    assets={path:FakeAsset(path) for path in
            ("/Game/Films/Root","/Game/Films/Shot_01","/Game/Films/Shot_02")}
    parent=assets["/Game/Films/Root"]
    tracks={asset:[] for asset in assets.values()}
    def add(seq,cls):
        assert cls is track_class
        value=FakeTrack()
        tracks[seq].append(value)
        return value
    def remove(seq,track):
        tracks[seq].remove(track)
        return True
    def get_start(section):
        if corrupt:
            return NS(value=section.range[0]+1)
        return NS(value=section.range[0])
    track_class=object()
    api=NS(load_asset=lambda path:assets.get(path),
           MovieSceneCinematicShotTrack=track_class,
           MovieSceneSequenceExtensions=NS(
               add_track=add,get_tracks=lambda seq:tracks[seq],
               remove_master_track=remove,
           ),
           MovieSceneSectionExtensions=NS(
               get_start_frame=get_start,
               get_end_frame=lambda section:NS(value=section.range[1]),
           ),
           EditorAssetLibrary=NS(save_loaded_asset=lambda seq:save))
    return api,parent,tracks


def test_nested_source_shots_compile_with_exact_frame_coverage_and_digest():
    csir,approval=_scene()
    plan=shots.compile_shots(csir,approval,csir_sha256="a"*64)
    assert plan["shots"]==[
        {"section_id":"s0","child_sequence_path":"/Game/Films/Shot_01",
         "start_frame":0,"end_frame":20},
        {"section_id":"s1","child_sequence_path":"/Game/Films/Shot_02",
         "start_frame":20,"end_frame":48},
    ]
    assert len(plan["canonical_plan_sha256"])==64
    assert plan["native_shots_generated"] is False


@pytest.mark.parametrize("mutation,match",[
    (lambda c,a:a["shots"].pop(),"roster"),
    (lambda c,a:a["shots"][0].__setitem__(
        "child_sequence_path",a["parent_sequence_path"]),"self-referential"),
    (lambda c,a:c["tracks"][0]["sections"][1].__setitem__(
        "start",_time(19)),"nonoverlapping"),
    (lambda c,a:c["tracks"][0]["sections"][1].__setitem__(
        "start",_time(21)),"nonoverlapping"),
    (lambda c,a:c["tracks"][0]["sections"][1].__setitem__(
        "time_scale",0.5),"blend/retime"),
    (lambda c,a:c["tracks"][0]["sections"][0].__setitem__(
        "native_payload",{"blend_in_seconds":0.25}),"blend/retime"),
    (lambda c,a:c["tracks"][0].__setitem__(
        "time_warp","custom") ,"retiming"),
    (lambda c,a:c["tracks"][0]["sections"][1].__setitem__(
        "end",_time(49)),"duration"),
    (lambda c,a:a.__setitem__(
        "source_csir_sha256","b"*64),"source-specific"),
])
def test_nested_shots_fail_closed_on_untrusted_time_or_identity(mutation,match):
    csir,approval=_scene()
    mutation(csir,approval)
    with pytest.raises(shots.NativeShotError,match=match):
        shots.compile_shots(csir,approval,csir_sha256="a"*64)


def test_native_shots_are_written_only_after_all_children_pass_and_saved():
    csir,approval=_scene()
    plan=shots.compile_shots(csir,approval,csir_sha256="a"*64)
    api,parent,tracks=_api()
    result=shots.realize(api,csir,approval,plan,source_sha256="a"*64)
    assert result["status"]=="SAVED_NATIVE_SHOTS_REOPENED_CINETWIN_PENDING"
    assert result["shot_count"]==2
    assert len(tracks[parent])==1
    assert [section.range for section in tracks[parent][0].sections]==[
        (0,20),(20,48)]
    assert result["new_editor_process_readback_verified"] is False


def test_native_shot_save_failure_rolls_back_every_section():
    csir,approval=_scene()
    plan=shots.compile_shots(csir,approval,csir_sha256="a"*64)
    api,parent,tracks=_api(save=False)
    with pytest.raises(shots.NativeShotError,match="save"):
        shots.realize(api,csir,approval,plan,source_sha256="a"*64)
    assert not tracks[parent]


def test_native_shot_readback_error_rolls_back_entire_track():
    csir,approval=_scene()
    plan=shots.compile_shots(csir,approval,csir_sha256="a"*64)
    api,parent,tracks=_api(corrupt=True)
    with pytest.raises(shots.NativeShotError,match="differs"):
        shots.realize(api,csir,approval,plan,source_sha256="a"*64)
    assert not tracks[parent]


def test_native_shot_refuses_changed_plan_or_occupied_parent_before_write():
    csir,approval=_scene()
    plan=shots.compile_shots(csir,approval,csir_sha256="a"*64)
    api,parent,tracks=_api()
    foreign=FakeTrack()
    tracks[parent].append(foreign)
    with pytest.raises(shots.NativeShotError,match="Existing"):
        shots.realize(api,csir,approval,plan,source_sha256="a"*64)
    assert tracks[parent]==[foreign]
    tracks[parent].clear()
    changed=copy.deepcopy(plan)
    changed["shots"][0]["end_frame"]=19
    with pytest.raises(shots.NativeShotError,match="differs"):
        shots.realize(api,csir,approval,changed,source_sha256="a"*64)
    assert not tracks[parent]
