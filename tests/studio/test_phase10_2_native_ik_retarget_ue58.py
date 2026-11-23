"""Unreal 5.8 typed IK retarget batch call with exact native asset receipts."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"integrations"/"unreal"))

import studio_ik_retarget as retarget


class Asset:
    def __init__(self,path,category,skeleton=None):
        self.path=path
        self.category=category
        self.skeleton=skeleton
    def get_path_name(self):
        return self.path+"."+self.path.rsplit("/",1)[1]
    def get_class(self):
        return NS(get_name=lambda:self.category)
    def get_editor_property(self,name):
        assert name=="skeleton"
        return self.skeleton


class Inputs:
    def __init__(self):
        self.fields={}
    def set_editor_property(self,k,v):
        self.fields[k]=v


def _fake(*,wrong=False):
    skeleton=Asset("/Game/Rigs/SK_Target","Skeleton")
    imported=Asset(
        "/Game/Anim/AS_Walk" if wrong else "/Game/Anim/AS_Source",
        "AnimSequence",skeleton,
    )
    generated=Asset(
        "/Game/Out/AS_Walk" if not wrong else "/Game/Out/WrongName",
        "AnimSequence",skeleton,
    )
    recorded=[]
    api=NS(
        EditorAssetLibrary=NS(
            does_asset_exist=lambda path:False,
            find_asset_data=lambda path: NS(path=path),
            save_loaded_asset=lambda clip:True,
        ),
        IKRetargetBatchOperationInputs=Inputs,
        IKRetargetBatchOperation=NS(
            run_batch_retarget=lambda values:(
                recorded.append(values.fields) or [NS(get_asset=lambda:generated)]
            ),
        ),
    )
    row={
        "source_animation_path":"/Game/Anim/AS_Walk",
        "target_asset_path":"/Game/Out/AS_Walk",
    }
    approved={
        "target":Asset("/Game/Rigs/SKM_Target","SkeletalMesh",skeleton),
        "retargeter":Asset("/Game/Rigs/IK_Retarget","IKRetargeter"),
    }
    staged=Asset("/Game/Rigs/SKM_Source","SkeletalMesh")
    return api,row,staged,approved,recorded


def test_ue58_typed_batch_retarget_no_overwrite_and_exact_native_skeleton():
    api,row,staged,approved,recorded=_fake()
    retarget.duplicate_clip(api,row,staged,approved)
    assert len(recorded)==1
    data=recorded[0]
    assert data["source_mesh"] is staged
    assert data["target_mesh"] is approved["target"]
    assert data["ik_retarget_asset"] is approved["retargeter"]
    assert data["target_path"]=="/Game/Out"
    assert data["include_referenced_assets"] is False
    assert data["overwrite_existing_files"] is False


def test_ue58_typed_batch_refuses_foreign_generated_clip_path():
    api,row,staged,approved,_=_fake(wrong=True)
    with pytest.raises(retarget.RetargetError,match="does not match"):
        retarget.duplicate_clip(api,row,staged,approved)


def test_typed_batch_refuses_unsupported_reflection_without_mutating():
    api,row,staged,approved,_=_fake()
    api.IKRetargetBatchOperationInputs=lambda:object()
    with pytest.raises(retarget.RetargetError,match="not reflected"):
        retarget.duplicate_clip(api,row,staged,approved)
