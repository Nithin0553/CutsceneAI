"""Phase 10.2: original Unity camera curves -> bounded full-frame native plan.

All tests are software-only; no Unity or Unreal Editor was launched.
"""
from __future__ import annotations

import copy
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT / "integrations/unreal", ROOT / "tests/unreal"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import csir_plan
import studio_camera_motion_contract as contract
from test_csir_plan import _curve, _fixture, _rt


def _camera(csir):
    return next(item for item in csir["tracks"]
                if item["ced_type"] == "camera.transform")


def _motion(csir, mapping):
    plan = csir_plan.build_plan(csir, mapping)
    tracks = [a for a in plan["actions"]
              if a.get("source_behavior_strategy") == contract.STRATEGY]
    assert len(tracks) == 1
    return plan, tracks[0]


def test_camera_full_frame_baking_includes_source_curve_interpolation_and_end():
    csir, mapping = _fixture()
    plan, action = _motion(csir, mapping)
    assert action["baked_source_curves"] is True
    assert action["frame_grid_first"] == 0
    assert action["frame_grid_last"] == 600
    assert action["frame_grid_sample_count"] == 601
    assert action["native_transform_channels_required"] == 9
    assert [x["frame"] for x in action["keys"]] == list(range(601))
    assert action["keys"][0]["location_cm"] == pytest.approx((300, 400, 120))
    assert action["keys"][-1]["location_cm"] == pytest.approx((300, 400, 120))
    a=action["keys"][450]["rotation_rpy_degrees"]
    expected=csir_plan.canonical_quat_to_unreal_rotator(
        csir_plan.unity_euler_delta_to_canonical_quat(0,0,2.5)
    )
    assert a == pytest.approx(expected,abs=1e-6)
    assert all(key["time_seconds"] == pytest.approx(key["frame"]/60)
               for key in action["keys"])
    assert contract.validate_plan(plan)[0]["status"] == (
        "SOURCE_GRID_VALIDATED_NATIVE_UNVERIFIED"
    )
    assert action["reopened_cinetwin_verified"] is False
    assert action["rendered_camera_motion_verified"] is False


def test_off_grid_source_keys_never_replace_or_erase_native_display_samples():
    csir, mapping = _fixture()
    track = _camera(csir)
    z = next(x for x in track["sections"][0]["payload"]["animation"]["curves"]
             if x.get("property_name")=="localEulerAnglesRaw.z")
    z["keys"]=[{"time_seconds":0.125,"value":5.},
               {"time_seconds":9.875,"value":27.}]
    _,action=_motion(csir,mapping)
    assert len(action["keys"])==601
    assert action["keys"][0]["frame"]==0
    assert action["keys"][-1]["frame"]==600
    # Source-time fractional keys are evaluated rather than individually
    # rounded to the nearest native display frame.
    half=action["keys"][300]["rotation_rpy_degrees"]
    expected_z=5 + (27-5)*(5.0-0.125)/(9.875-0.125)
    expected=csir_plan.canonical_quat_to_unreal_rotator(
        csir_plan.unity_euler_delta_to_canonical_quat(0,0,expected_z)
    )
    assert half==pytest.approx(expected,abs=1e-6)


def test_adjacent_camera_clips_identical_shared_pose_can_bake_contiguously():
    csir,mapping=_fixture()
    track=_camera(csir)
    first=copy.deepcopy(track["sections"][0])
    second=copy.deepcopy(first)
    first["end"]=_rt(5.)
    second["start"]=_rt(5.)
    second["source_offset"]=_rt(5.)
    track["sections"]=[first,second]
    _,action=_motion(csir,mapping)
    assert len(action["keys"])==601
    assert action["keys"][300]["frame"]==300
    assert action["keys"][301]["frame"]==301
    assert contract.validate_action(action,duration_frames=600)["sample_count"]==601


def test_single_clip_retime_uses_original_source_offset_and_speed():
    csir,mapping=_fixture()
    track=_camera(csir)
    track["sections"][0]["source_offset"]=_rt(2.)
    track["sections"][0]["time_scale"]=0.5
    _,action=_motion(csir,mapping)
    assert len(action["keys"])==601
    # Timeline t=6 -> source t=5, which is the first authored Z-rotation key.
    assert action["keys"][360]["rotation_rpy_degrees"]==pytest.approx((0,0,0))
    # Timeline t=10 -> source t=7, yielding Unity local Euler Z=2 deg.
    expected=csir_plan.canonical_quat_to_unreal_rotator(
        csir_plan.unity_euler_delta_to_canonical_quat(0,0,2.)
    )
    assert action["keys"][600]["rotation_rpy_degrees"]==pytest.approx(
        expected,abs=1e-6
    )


def test_camera_rotation_only_keeps_original_static_source_position():
    csir,mapping=_fixture()
    track=_camera(csir)
    curves=track["sections"][0]["payload"]["animation"]["curves"]
    track["sections"][0]["payload"]["animation"]["curves"]=[
        x for x in curves
        if not str(x.get("canonical_semantic") or "").startswith(
            "transform.infinite_offset.position."
        )
    ]
    camera=next(e for e in csir["entities"] if e["ced_type"]=="entity.camera")
    camera["metadata"]["world_transform"]={
        "position":{"x":3.,"y":4.,"z":-5.},
        "rotation":{"x":0.,"y":0.,"z":0.,"w":1.},
        "scale":{"x":1.,"y":1.,"z":1.},
    }
    _,action=_motion(csir,mapping)
    assert action["keys"][0]["location_cm"]==pytest.approx((500,300,400))
    assert action["keys"][350]["location_cm"]==pytest.approx((500,300,400))


def test_camera_position_only_keeps_original_static_world_orientation():
    csir,mapping=_fixture()
    track=_camera(csir)
    curves=track["sections"][0]["payload"]["animation"]["curves"]
    track["sections"][0]["payload"]["animation"]["curves"]=[
        x for x in curves
        if not str(x.get("canonical_semantic") or "").startswith(
            "transform.infinite_offset.rotation."
        )
        and not str(x.get("property_name") or "").startswith("localEulerAnglesRaw.")
    ]+[_curve("transform.position.x",[(0.,1.),(10.,3.)])]
    camera=next(e for e in csir["entities"] if e["ced_type"]=="entity.camera")
    q=csir_plan.unity_euler_delta_to_canonical_quat(0,0,30)
    camera["metadata"]["world_transform"]={
        "position":{"x":1.,"y":2.,"z":3.},
        "rotation":dict(zip("xyzw",q)),
        "scale":{"x":1.,"y":1.,"z":1.},
    }
    _,action=_motion(csir,mapping)
    expected=csir_plan.canonical_quat_to_unreal_rotator(q)
    assert action["keys"][0]["rotation_rpy_degrees"]==pytest.approx(expected)
    assert action["keys"][300]["rotation_rpy_degrees"]==pytest.approx(expected)
    assert action["keys"][-1]["location_cm"]==pytest.approx((300,700,120))


@pytest.mark.parametrize("mutate,reason", [
    (lambda csir: _camera(csir)["sections"][0].update(
        start=_rt(1/120)), "align"),
    (lambda csir: _camera(csir)["sections"][0].update(
        end=_rt(9.991666666666667)), "align"),
    (lambda csir: _camera(csir)["sections"][0].update(time_scale=0),
     "clip speed"),
    (lambda csir: _camera(csir)["sections"][0].update(time_scale=float("nan")),
     "clip speed"),
    (lambda csir: _camera(csir)["sections"].append({
        **copy.deepcopy(_camera(csir)["sections"][0]),
        "start":_rt(9.),"end":_rt(10.),
    }), "Overlapping"),
    (lambda csir: _camera(csir)["sections"].append({
        **copy.deepcopy(_camera(csir)["sections"][0]),
        "start":_rt(11.),"end":_rt(12.),
    }), "gaps"),
    (lambda csir: csir["tracks"].append(copy.deepcopy(_camera(csir))),
     "Multiple active"),
    (lambda csir: _camera(csir)["sections"][0]["payload"]["animation"]["curves"].append(
        _curve("unsupported.native.camera_state",[(0,1.)])), "Unrecognized"),
    (lambda csir: _camera(csir)["sections"][0]["payload"]["animation"]["curves"].append(
        _curve("transform.infinite_offset.position.x",[(0,1.)],property_name="m_LocalPosition.x")),
     "Duplicate"),
    (lambda csir: _camera(csir)["sections"][0]["payload"]["animation"]["curves"].append(
        dict(_curve("transform.position.x",[(0,1.)]),path="Pivot/Child")),
     "Nested"),
])
def test_camera_compiler_blocks_ambiguous_source_timelines(mutate,reason):
    csir,mapping=_fixture()
    mutate(csir)
    with pytest.raises(csir_plan.PlanError,match=reason):
        csir_plan.build_plan(csir,mapping)


def test_camera_adjacent_clip_pose_discontinuity_is_not_implicit_blending():
    csir,mapping=_fixture()
    track=_camera(csir)
    first=copy.deepcopy(track["sections"][0])
    second=copy.deepcopy(first)
    first["end"]=_rt(5.)
    second["start"]=_rt(5.)
    second["source_offset"]=_rt(5.)
    curves=second["payload"]["animation"]["curves"]
    x=next(c for c in curves
           if c.get("canonical_semantic")=="transform.infinite_offset.position.x")
    x["keys"][0]["value"]=7.
    track["sections"]=[first,second]
    with pytest.raises(csir_plan.PlanError,match="discontinuous shared pose"):
        csir_plan.build_plan(csir,mapping)


def test_camera_missing_source_baseline_does_not_guess_world_origin():
    csir,mapping=_fixture()
    track=_camera(csir)
    track["sections"][0]["payload"]["animation"]["curves"]=[
        x for x in track["sections"][0]["payload"]["animation"]["curves"]
        if not str(x.get("canonical_semantic") or "").startswith(
            "transform.infinite_offset.position."
        )
    ]
    with pytest.raises(csir_plan.PlanError,match="world transform"):
        csir_plan.build_plan(csir,mapping)


def test_camera_mixed_quaternion_euler_ownership_is_rejected():
    csir,mapping=_fixture()
    track=_camera(csir)
    curves=track["sections"][0]["payload"]["animation"]["curves"]
    for axis,val in zip("xyzw",(0.,0.,0.,1.)):
        curves.append(_curve("transform.rotation."+axis,[(0.,val),(10.,val)]))
    with pytest.raises(csir_plan.PlanError,match="conflict"):
        csir_plan.build_plan(csir,mapping)


def test_camera_infinite_offset_is_one_constant_authoring_value():
    csir,mapping=_fixture()
    curve=next(x for x in _camera(csir)["sections"][0]["payload"]["animation"]["curves"]
               if x.get("canonical_semantic")=="transform.infinite_offset.position.x")
    curve["keys"].append({"time_seconds":1.,"value":9.})
    with pytest.raises(csir_plan.PlanError,match="offsets"):
        csir_plan.build_plan(csir,mapping)


@pytest.mark.parametrize("tamper",[
    lambda a:a["keys"].pop(),
    lambda a:a["keys"][100].update(frame=99),
    lambda a:a["keys"][100].update(frame=9999),
    lambda a:a["keys"][200].update(location_cm=(float("nan"),0,0)),
    lambda a:a["keys"][300].update(rotation_rpy_degrees=(0,0,float("inf"))),
    lambda a:a.update(frame_grid_sample_count=2),
    lambda a:a.update(native_transform_channels_required=6),
    lambda a:a.update(baked_source_curves=False),
    lambda a:a["keys"][400].update(rotation_rpy_degrees=(0,0,179)),
])
def test_native_preflight_rejects_modified_or_incomplete_camera_grid(tamper):
    csir,mapping=_fixture()
    plan,action=_motion(csir,mapping)
    tamper(action)
    with pytest.raises(contract.CameraMotionContractError):
        contract.validate_plan(plan)


def test_ordinary_prop_motion_retains_legacy_sparse_source_keys():
    csir,mapping=_fixture()
    plan=csir_plan.build_plan(csir,mapping)
    prop=next(x for x in plan["actions"]
              if x.get("entity_name")=="MOVING_PROP" and x["kind"]=="transform")
    assert len(prop["keys"])==3
    assert prop.get("source_behavior_strategy")!=contract.STRATEGY
    assert len(contract.validate_plan(plan))==1



def test_eased_camera_clip_refuses_local_curve_inference_without_capture():
    csir,mapping=_fixture()
    _camera(csir)["sections"][0]["native_payload"]={
        "ease_in_seconds":0.4,"blend_in_seconds":-1,
    }
    with pytest.raises(csir_plan.PlanError,match="evaluated CineTwin"):
        csir_plan.build_plan(csir,mapping)


def test_camera_parent_with_its_own_animation_requires_evaluated_world_capture():
    csir,mapping=_fixture()
    csir["entities"].append({
        "entity_id":"entity:camera_rig",
        "name":"MovingCameraRig","ced_type":"entity.prop",
        "metadata":{"world_transform":{
            "position":{"x":0,"y":0,"z":0},
            "rotation":{"x":0,"y":0,"z":0,"w":1},
            "scale":{"x":1,"y":1,"z":1},
        }},
    })
    camera=next(e for e in csir["entities"] if e["ced_type"]=="entity.camera")
    camera["parent_entity_id"]="entity:camera_rig"
    csir["tracks"].append({
        "track_id":"rig:anim","ced_type":"animation.track",
        "binding_entity_id":"entity:camera_rig",
        "sections":[{
            "start":_rt(0),"end":_rt(10),
            "payload":{"animation":{"curves":[
                _curve("transform.position.y",[(0,0),(10,2)])
            ]}},
        }],
    })
    mapping["entities"]["MovingCameraRig"]={"actor_label":"UECameraRig"}
    with pytest.raises(csir_plan.PlanError,match="parent trajectory"):
        csir_plan.build_plan(csir,mapping)


def test_duplicate_unity_euler_hint_and_raw_axis_is_rejected():
    csir,mapping=_fixture()
    curves=_camera(csir)["sections"][0]["payload"]["animation"]["curves"]
    curves.append(_curve("transform.rotation.euler_native",[(0,10)],
                        property_name="m_LocalEulerAnglesHint.x"))
    with pytest.raises(csir_plan.PlanError,match="Duplicate camera"):
        csir_plan.build_plan(csir,mapping)


def test_unknown_camera_semantic_with_known_prefix_must_be_rejected():
    csir,mapping=_fixture()
    curves=_camera(csir)["sections"][0]["payload"]["animation"]["curves"]
    curves.append(_curve("transform.rotation.unknown_euler_axis",[(0,10)]))
    with pytest.raises(csir_plan.PlanError,match="Unrecognized"):
        csir_plan.build_plan(csir,mapping)
