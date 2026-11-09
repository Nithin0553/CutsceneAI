"""Runtime-independent hierarchy-local coordinate conversion tests."""
import math
import sys
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[2]
for relative in ("integrations/unreal","packages/cinetwin","packages/studio"):
    sys.path.insert(0,str(ROOT/relative))
import hierarchy_local


def _pose(position, quat=(0.0,0.0,0.0,1.0), scale=(1,1,1)):
    return {
        "position_m":list(position),
        "rotation_xyzw":list(quat),
        "scale_xyz":list(scale),
    }


def test_parent_quarter_turn_inverse_yields_correct_local_translation_and_rotation():
    root_2=math.sqrt(.5)
    parent=_pose((10.0,0.0,0.0),(0.0,root_2,0.0,root_2))
    child=_pose((10.0,0.0,-2.0),(0.0,root_2,0.0,root_2))
    pos,rot=hierarchy_local._relative(parent,child)
    assert pos == pytest.approx((2.0,0.0,0.0),abs=1e-9)
    assert rot == pytest.approx((0.0,0.0,0.0,1.0),abs=1e-9)


def test_nonzero_uniform_parent_scale_is_inverted_in_parent_local_space():
    parent=_pose((1.0,0.0,0.0),scale=(2.0,2.0,2.0))
    child=_pose((5.0,0.0,0.0))
    pos,rot=hierarchy_local._relative(parent,child)
    assert pos == (2.0,0.0,0.0)
    assert rot == (0.0,0.0,0.0,1.0)


def test_invalid_zero_scale_refused_before_sequencer_construction():
    with pytest.raises(hierarchy_local.HierarchyLocalError,match="zero world scale"):
        hierarchy_local._relative(_pose((0,0,0),scale=(0,1,1)),_pose((1,0,0)))


def test_missing_source_frame_refused_not_interpolated_from_unknown_physics():
    src={
        "timing":{
            "source_rate":{"numerator":2,"denominator":1},
            "playback_start":{"value":0,"rate":{"numerator":1,"denominator":1}},
            "playback_end":{"value":2,"rate":{"numerator":1,"denominator":1}},
        }
    }
    capture={"samples":[
        {"time_seconds":0.0,"entities":[
            {"entity_id":"child","world_transform":_pose((2,0,0))},
            {"entity_id":"parent","world_transform":_pose((1,0,0))},
        ]}
    ]}
    with pytest.raises(hierarchy_local.HierarchyLocalError,match="Missing source frame"):
        hierarchy_local.bake_parent_local(
            src,capture,child_id="child",parent_id="parent",
            child_name="Child",actor_label="ChildActor"
        )
