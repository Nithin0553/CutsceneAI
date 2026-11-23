"""Phase 10.2 consolidated matrix tests (synthetic, not real engine acceptance)."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"packages"/"studio"))
sys.path.insert(0,str(ROOT/"integrations"/"unreal"))

import phase10_2_consolidated_audit as audit

RATE={"numerator":2,"denominator":1}


def _time(sec):
    return {"value":sec*2,"rate":RATE}


def _source():
    csir={
        "kind":"cutsceneai.csir","cutscene_id":"phase10-2-test",
        "source":{"engine":"unity","project_fingerprint":"synthetic"},
        "timing":{
            "source_rate":RATE,"display_rate":RATE,
            "playback_start":_time(0),"playback_end":_time(2),
            "duration_seconds":2.,
        },
        "assets":[
            {"asset_id":"fx","ced_type":"vfx.particles","name":"Smoke"},
            {"asset_id":"shader","ced_type":"shader.custom","name":"CustomShader"},
        ],
        "entities":[
            {"entity_id":"cam","name":"Camera","ced_type":"entity.camera"},
            {"entity_id":"left","name":"Left","ced_type":"entity.character"},
            {"entity_id":"right","name":"Right","ced_type":"entity.character"},
        ],
        "tracks":[
            {"track_id":"shot","ced_type":"camera.cut","sections":[
                {"start":_time(0),"end":_time(2)}
            ]},
            {"track_id":"audio","ced_type":"audio.track","sections":[]},
            {"track_id":"motion","ced_type":"animation.track",
             "binding_entity_id":"left","sections":[
                 {"start":_time(0),"end":_time(2)},
             ]},
        ],
        "relationships":[],
    }
    mapping={"entities":{
        "Camera":{"actor_label":"CineCam"},
        "Left":{"actor_label":"LeftNative"},
        "Right":{"actor_label":"RightNative"},
    }}
    plan={
        "duration_frames":4,
        "actions":[
            {"kind":"camera_cut","source_location":"tracks[0]"},
            {"kind":"audio","source_location":"tracks[1]"},
            {"kind":"skeletal_animation","source_location":"tracks[2]"},
        ],
    }
    samples=[]
    for i in range(5):
        t=i/2
        samples.append({
            "time_seconds":t,
            "entities":[
                {"entity_id":eid,"actor_label":lab,
                 "world_transform":{
                     "position_m":[t+offset,0.,0.],
                     "rotation_xyzw":[0.,0.,0.,1.],
                 }}
                for eid,lab,offset in (
                    ("left","LeftNative",0.),
                    ("right","RightNative",2.),
                )
            ],
        })
    capture={"cutscene_id":"phase10-2-test","samples":samples}
    return csir,mapping,plan,capture


def test_phase10_2_all_seven_original_workstreams_are_exact_and_reported():
    csir,mapping,plan,capture=_source()
    result=audit.audit(csir,mapping,plan,
                       source_capture=capture,target_capture=capture)
    assert result["workstream_count"]==7
    assert [r["work_area_id"] for r in result["workstreams"]]==[
        x[0] for x in audit.WORK_AREAS
    ]
    assert result["fully_accepted_workstream_count"]==0
    assert len(result["known_guarded_repair_families"])==12
    assert result["source_occurrences_accounted"]==result[
        "source_occurrences_total"]
    assert all(not r["work_area_fully_complete"] and
               not r["rendered_fidelity_verified"] for r in result["workstreams"])
    assert result["real_unity_editor_executed"] is False
    assert result["native_mutation_authorized"] is False
    assert result["release_candidate_ready"] is False
    assert audit.verify(result,csir,mapping,plan,
                        source_capture=capture,target_capture=capture)


def test_phase10_2_reports_actual_scene_camera_shots_characters_effects():
    csir,mapping,plan,capture=_source()
    result=audit.audit(csir,mapping,plan,source_capture=capture)
    areas={a["work_area_id"]:a for a in result["workstreams"]}
    assert areas["animated_camera"]["software_contract_evidence"][
        "source_camera_count"]==1
    assert areas["timeline"]["software_contract_evidence"][
        "camera_cut_sections"]==1
    assert areas["moving_character"]["software_contract_evidence"][
        "common_source_frame_grid_available"] is True
    sync=areas["multi_character"]["software_contract_evidence"][
        "multi_character_source_grid"]
    assert sync["source_character_count"]==2
    assert sync["shared_frame_count"]==5
    assert areas["effects"]["software_contract_evidence"][
        "source_effect_occurrence_count"]==3


def test_phase10_2_missing_capture_is_visible_not_a_successful_conversion():
    csir,mapping,plan,_=_source()
    result=audit.audit(csir,mapping,plan)
    areas={x["work_area_id"]:x for x in result["workstreams"]}
    assert areas["moving_character"]["software_contract_evidence"][
        "common_source_frame_grid_available"] is False
    assert areas["multi_character"]["software_contract_evidence"][
        "multi_character_source_grid"] is None
    assert result["full_phase10_2_accepted"] is False


def test_phase10_2_unknown_plugin_and_unregistered_action_cannot_disappear():
    csir,mapping,plan,capture=_source()
    extra=copy.deepcopy(csir)
    extra["assets"].append({
        "asset_id":"vendor","name":"Vendor","ced_type":"plugin.vendor_special",
    })
    result=audit.audit(extra,mapping,plan,source_capture=capture)
    assert result["source_occurrences_total"]==(
        audit.audit(csir,mapping,plan,source_capture=capture)[
            "source_occurrences_total"]+1
    )
    unsafe=copy.deepcopy(plan)
    unsafe["actions"].append({"kind":"write_custom_vfx_code","source_location":"assets[0]"})
    with pytest.raises(audit.Phase10_2AuditError):
        audit.audit(csir,mapping,unsafe)


def test_phase10_2_mismatched_capture_identity_and_forged_report_rejected():
    csir,mapping,plan,capture=_source()
    mismatched=copy.deepcopy(capture)
    mismatched["cutscene_id"]="other-job"
    with pytest.raises(audit.Phase10_2AuditError,match="identity"):
        audit.audit(csir,mapping,plan,source_capture=mismatched)
    with pytest.raises(audit.Phase10_2AuditError,match="without"):
        audit.audit(csir,mapping,plan,target_capture=capture)
    result=audit.audit(csir,mapping,plan,source_capture=capture)
    result["workstreams"][0]["work_area_fully_complete"]=True
    assert not audit.verify(result,csir,mapping,plan,source_capture=capture)


def test_phase10_2_manifest_matches_actual_langgraph_and_native_dispatch():
    import studio_agent_graph as graph
    assert set(audit.ADAPTER_SCOPE)==graph.ALLOWED_STRATEGIES-{"report_only"}
    dispatch=(ROOT/"integrations"/"unreal"/"studio_agent_executor.py").read_text(
        encoding="utf-8"
    )
    assert all('"' + strategy + '"' in dispatch
               for strategy in audit.ADAPTER_SCOPE)
