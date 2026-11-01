"""Source-authored linear scalar curves into explicit native Unreal float tracks."""
from __future__ import annotations

import copy
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for part in ("integrations/unreal", "packages/cinetwin", "packages/studio"):
    sys.path.insert(0, str(ROOT / part))

import scalar_property_adapter as scalar
import transfer_backend
from test_transfer_backend import mapping, rt, source


def fixture():
    src, target = source(), mapping()
    curve = {
        "canonical_semantic": "custom.light_temperature",
        "component_type": "MyGame.CustomLight",
        "keys": [
            {"time_seconds": 0, "value": 10.0, "in_tangent": 5,
             "out_tangent": 5, "weighted_mode": 0},
            {"time_seconds": 2, "value": 20.0, "in_tangent": 5,
             "out_tangent": 5, "weighted_mode": 0},
        ],
    }
    track = {
        "track_id": "custom-scalar", "name": "Custom Temp",
        "ced_type": "plugin.custom_scalar",
        "binding_entity_id": "moving",
        "sections": [{
            "section_id": "s", "start": rt(0), "end": rt(2),
            "source_offset": rt(0), "time_scale": 1.0,
            "payload": {"animation": {"curves": [curve]}},
        }],
    }
    src["tracks"].append(track)
    target["scalar_property_mappings"] = [{
        "source_semantic": "custom.light_temperature",
        "source_component_type": "MyGame.CustomLight",
        "source_entity_name": "MOVING_PROP",
        "target_scope": "component",
        "target_class": "PointLightComponent",
        "target_property_name": "Temperature",
        "target_property_path": "Temperature",
        "value_scale": 2.0,
        "value_offset": 100.0,
    }]
    return src, target, track, curve


def test_source_linear_key_conversion_creates_native_typed_property_action():
    src, target, track, _curve = fixture()
    original = copy.deepcopy(src)
    actions = scalar.build_actions(src, target, track)
    assert len(actions) == 1
    item = actions[0]
    assert item["kind"] == "property_float"
    assert item["entity_name"] == "MOVING_PROP"
    assert item["target_class"] == "PointLightComponent"
    assert item["target_property_name"] == "Temperature"
    assert item["keys"] == [
        {"frame": 0, "value": 120.0},
        {"frame": 4, "value": 140.0},
    ]
    assert item["fidelity_status"].endswith("UNVERIFIED")
    assert src == original


def test_generic_scalar_property_is_wired_into_real_transfer_backend():
    src, mapping_data, _track, _curve = fixture()
    plan, report = transfer_backend.compose(src, mapping_data)
    assert any(a["kind"] == "property_float" for a in plan["actions"])
    assert report["feature_dispatch"]["unknown_action_kinds"] == []
    assert report["tracks"][-1]["outcome"] in {
        "NATIVE_PARTIAL", "NATIVE_UNVERIFIED"}
    assert report["no_full_fidelity_claim"] is True


def test_empty_or_unrelated_source_track_is_not_claimed_by_scalar_adapter():
    src, mapping_data, track, _curve = fixture()
    other = copy.deepcopy(track)
    other["sections"] = [{"payload": {"animation": {"curves": []}}}]
    assert scalar.build_actions(src, mapping_data, other) == []


@pytest.mark.parametrize("violation", [
    "nonlinear", "weighted", "no_tangent", "subframe",
    "wrong_component", "nonnumeric", "zero_scale",
    "invalid_target_path", "duplicate_target", "multisection",
])
def test_ambiguous_property_transfer_is_never_silently_linearized(violation):
    src, target, track, curve = fixture()
    spec = target["scalar_property_mappings"][0]
    if violation == "nonlinear":
        curve["keys"][0]["out_tangent"] = 0
    elif violation == "weighted":
        curve["keys"][0]["weighted_mode"] = 1
    elif violation == "no_tangent":
        curve["keys"][0].pop("out_tangent")
    elif violation == "subframe":
        curve["keys"][0]["time_seconds"] = 0.125
    elif violation == "wrong_component":
        curve["component_type"] = "UnrelatedType"
        # Mismatched source class is unrecognized, not an invalid conversion.
        assert scalar.build_actions(src, target, track) == []
        return
    elif violation == "nonnumeric":
        curve["keys"][0]["value"] = "not a number"
    elif violation == "zero_scale":
        spec["value_scale"] = 0
    elif violation == "invalid_target_path":
        spec["target_property_path"] = "bHidden;exec('bad')"
    elif violation == "duplicate_target":
        target["scalar_property_mappings"].append(copy.deepcopy(spec))
    elif violation == "multisection":
        track["sections"].append(copy.deepcopy(track["sections"][0]))
    with pytest.raises(scalar.ScalarPropertyError):
        scalar.build_actions(src, target, track)


def test_nonfinite_scalar_mapping_is_invalid_and_source_unchanged():
    src, target, track, _curve = fixture()
    original = copy.deepcopy(src)
    target["scalar_property_mappings"][0]["value_offset"] = math.inf
    with pytest.raises(scalar.ScalarPropertyError, match="offset"):
        scalar.build_actions(src, target, track)
    assert src == original


def test_source_bound_scalar_mapping_does_not_consume_other_source_entity():
    src, mapping_data, track, _curve = fixture()
    track["binding_entity_id"] = "lens"
    assert scalar.build_actions(src, mapping_data, track) == []


def test_ue_builder_contains_float_track_preflight_and_realization():
    code = (ROOT / "integrations/unreal" / "build_level_sequence.py"
            ).read_text(encoding="utf-8")
    assert "def _target_scalar_object" in code
    assert 'elif kind == "property_float"' in code
    assert "MovieSceneFloatTrack" in code
    assert "get_editor_property" in code
    assert "add_linear_channel_key" in code
    assert "Property mapping overlaps" not in code


def test_duplicate_scalar_target_from_separate_tracks_is_blocked():
    src, target, track, _curve = fixture()
    other = copy.deepcopy(track)
    other["track_id"] = "another"
    src["tracks"].append(other)
    with pytest.raises(transfer_backend.TransferBackendError,
                       match="Multiple source tracks drive"):
        transfer_backend.compose(src, target)
