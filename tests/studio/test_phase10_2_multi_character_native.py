"""Multi-character Unreal Sequencer binding and attachment regression."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"integrations"/"unreal"))
import studio_multi_character_native as native


class Asset:
    def __init__(self,path,name="AnimSequence"):
        self.path=path
        self.name=name
    def get_path_name(self):
        return self.path+"."+self.path.rsplit("/",1)[1]
    def get_class(self):
        return NS(get_name=lambda:self.name)


class Actor:
    def __init__(self,label,parent=None):
        self.label=label
        self.parent=parent
    def get_actor_label(self):
        return self.label
    def get_attach_parent_actor(self):
        return self.parent


class Section:
    def __init__(self,clip):
        self.clip=Asset(clip)
    def get_editor_property(self,key):
        assert key=="params"
        return NS(get_editor_property=lambda key:self.clip)
    def get_start_frame(self):
        return 0
    def get_end_frame(self):
        return 24


class Track:
    def __init__(self,clip):
        self.section=Section(clip)
    def get_class(self):
        return NS(get_name=lambda:"MovieSceneSkeletalAnimationTrack")
    def get_sections(self):
        return [self.section]


class Binding:
    def __init__(self,owner,clip):
        self.owner=owner
        self.track=Track(clip)
    def get_tracks(self):
        return [self.track]


def _setup():
    boss=Actor("BossUE")
    worker=Actor("WorkerUE",boss)
    bindings=[
        Binding(boss,"/Game/Anim/Boss"),
        Binding(worker,"/Game/Anim/Worker"),
    ]
    api=NS(
        MovieSceneSequenceExtensions=NS(
            get_bindings=lambda sequence:bindings,
            locate_bound_objects=lambda sequence,bind,world:[bind.owner],
        ),
        UnrealEditorSubsystem=object(),
        get_editor_subsystem=lambda cls:NS(get_editor_world=lambda:object()),
    )
    csir={"entities":[
        {"entity_id":"boss","name":"Boss","ced_type":"entity.character"},
        {"entity_id":"worker","name":"Worker","ced_type":"entity.character",
         "parent_entity_id":"boss"},
    ]}
    mapping={"entities":{
        "Boss":{"actor_label":"BossUE"},"Worker":{"actor_label":"WorkerUE"},
    }}
    plan={"actions":[
        {"kind":"skeletal_animation","entity_name":"Boss",
         "unreal_asset_path":"/Game/Anim/Boss","start_frame":0,"end_frame":24},
        {"kind":"skeletal_animation","entity_name":"Worker",
         "unreal_asset_path":"/Game/Anim/Worker","start_frame":0,"end_frame":24},
    ]}
    return api,bindings,csir,mapping,plan


def test_two_native_characters_have_exact_source_clip_ranges_and_parent_owner():
    api,_bindings,csir,mapping,plan=_setup()
    report=native.inspect(api,object(),csir,mapping,plan)
    assert report["status"]=="NATIVE_BINDINGS_AND_SECTION_TIMING_MATCH_ORIGINAL_PLAN"
    assert report["character_count"]==2
    assert [row["native_sections"] for row in report["characters"]]==[1,1]
    assert report["native_bone_pose_and_contact_verified"] is False
    assert report["reopened_independent_editor_verified"] is False


def test_native_character_refuses_wrong_section_or_attachment():
    api,bindings,csir,mapping,plan=_setup()
    bindings[0].track.section.get_end_frame=lambda:25
    with pytest.raises(native.NativeCoordinationError,match="sections"):
        native.inspect(api,object(),csir,mapping,plan)
    api,bindings,csir,mapping,plan=_setup()
    bindings[1].owner.parent=None
    with pytest.raises(native.NativeCoordinationError,match="parent"):
        native.inspect(api,object(),csir,mapping,plan)


def test_native_character_refuses_extra_root_owner_duplicate_mapping():
    api,bindings,csir,mapping,plan=_setup()
    bindings[0].track.get_class=lambda:NS(get_name=lambda:"MovieScene3DTransformTrack")
    with pytest.raises(native.NativeCoordinationError,match="sections"):
        native.inspect(api,object(),csir,mapping,plan)
    api,bindings,csir,mapping,plan=_setup()
    mapping["entities"]["Worker"]["actor_label"]="BossUE"
    with pytest.raises(native.NativeCoordinationError,match="unique"):
        native.inspect(api,object(),csir,mapping,plan)


def test_untrusted_plan_cannot_claim_new_actor_with_missing_native_binding():
    api,bindings,csir,mapping,plan=_setup()
    bindings.pop()
    with pytest.raises(native.NativeCoordinationError,match="lack native"):
        native.inspect(api,object(),csir,mapping,plan)


def test_native_ue58_sequencer_extension_section_frames_are_verified():
    api,bindings,csir,mapping,plan=_setup()
    api.MovieSceneSectionExtensions=NS(
        get_start_frame=lambda section:NS(value=0),
        get_end_frame=lambda section:NS(value=24),
    )
    for binding in bindings:
        binding.track.section.get_start_frame=lambda:(
            (_ for _ in ()).throw(RuntimeError("wrong legacy API"))
        )
    report=native.inspect(api,object(),csir,mapping,plan)
    assert report["character_count"]==2
    api.MovieSceneSectionExtensions.get_end_frame=lambda section:NS(value=25)
    with pytest.raises(native.NativeCoordinationError,match="sections"):
        native.inspect(api,object(),csir,mapping,plan)
