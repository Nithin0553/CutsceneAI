"""Synthetic per-frame six-domain behavior parity tests; not an engine certificate."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"packages"/"cinetwin"))
import phase10_2_effect_comparison as compare


def _record():
    sample={
        "lighting":[{"source_id":"sun","intensity":2000.,
                     "color_linear_rgb":[0.8,0.7,0.6],
                     "shadow_enabled":True}],
        "shaders_materials":[{"source_id":"surface",
                              "roughness":0.5,"metallic":0.2,"opacity":1.,
                              "linear_rgb":[0.8,0.1,0.1]}],
        "audio":[{"source_id":"voice","rms":0.2,"peak":0.4,"playing":True}],
        "vfx":[{"source_id":"smoke","alive_particles":12,
                "centroid_m":[1.,2.,3.]}],
        "events":[{"source_id":"signal","fire_count":1,"state_sha256":"c"*64}],
        "physics":[{"source_id":"body","position_m":[0,0,0],
                    "velocity_mps":[1,0,0],"angular_velocity_rps":[0,0,0],
                    "contact_ids":["ground"]}],
    }
    source={"source_csir_sha256":"a"*64,"samples":[
        {"time_seconds":0.,"effects":sample},
        {"time_seconds":1./30.,"effects":copy.deepcopy(sample)},
    ]}
    target=copy.deepcopy(source)
    target["target_project_sha256"]="b"*64
    return source,target


def _compare(s,t):
    return compare.compare(s,t,source_csir_sha256="a"*64,
                           target_project_sha256="b"*64)


def test_all_six_source_native_observed_effects_match_with_explicit_limits():
    source,target=_record()
    result=_compare(source,target)
    assert set(result["domains"])==set(compare.DOMAINS)
    assert result["source_frame_count"]==2
    assert result["status"]=="MEASURED_DOMAINS_WITHIN_TOLERANCE"
    assert all(row["measured_occurrences"]==2
               for row in result["domains"].values())
    assert result["rendered_audio_and_physics_fidelity_verified"] is False


@pytest.mark.parametrize("family,field,change",[
    ("lighting","intensity",1000),
    ("shaders_materials","roughness",0.9),
    ("audio","rms",0.7),
    ("vfx","alive_particles",13),
    ("events","fire_count",2),
    ("physics","velocity_mps",[100.,0.,0.]),
])
def test_each_cinematic_family_detects_an_independently_measured_difference(
        family,field,change):
    source,target=_record()
    target["samples"][1]["effects"][family][0][field]=change
    result=_compare(source,target)
    assert result["domains"][family]["status"]=="OBSERVED_BEHAVIOR_DIFFERENCE"
    assert result["status"]=="UNVERIFIED_OR_DIFFERENT"


def test_missing_unmeasured_domain_never_becomes_a_silent_pass():
    source,target=_record()
    for frame in target["samples"]:
        frame["effects"].pop("vfx")
    result=_compare(source,target)
    assert result["domains"]["vfx"]["status"]=="UNMEASURED_OR_SOURCE_OCCURRENCE_UNMAPPED"
    assert result["status"]=="UNVERIFIED_OR_DIFFERENT"


def test_foreign_native_editor_and_duplicate_frame_rejected():
    source,target=_record()
    target["source_csir_sha256"]="f"*64
    with pytest.raises(compare.EffectComparisonError,match="identity"):
        _compare(source,target)
    target["source_csir_sha256"]="a"*64
    target["samples"][1]["time_seconds"]=0
    with pytest.raises(compare.EffectComparisonError,match="grid"):
        _compare(source,target)


def test_foreign_effect_object_and_missing_event_state_never_pass():
    source,target=_record()
    target["samples"][0]["effects"]["audio"][0]["source_id"]="other"
    result=_compare(source,target)
    assert result["domains"]["audio"]["missing_samples"]==1
    target=copy.deepcopy(source)
    target["target_project_sha256"]="b"*64
    target["samples"][0]["effects"]["events"][0].pop("state_sha256")
    with pytest.raises(compare.EffectComparisonError,match="hash"):
        _compare(source,target)
