"""Source-bound mapping and transform conversion refusal regressions.

No Unity or Unreal Editor process is needed.  These test the shared software
contracts before the native builder can modify the target project.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for directory in (ROOT / "integrations" / "unreal", ROOT / "packages" / "studio"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import asset_resolver
import csir_plan


def _time(seconds: int) -> dict:
    return {"value": seconds, "rate": {"numerator": 1, "denominator": 1}}


def _source() -> dict:
    return {
        "schema_version": "0.1.0",
        "source": {"engine": "unity"},
        "timing": {
            "source_rate": {"numerator": 30, "denominator": 1},
            "duration_seconds": 1.0,
        },
        "assets": [],
        "entities": [{
            "entity_id": "guard-id", "name": "Guard", "ced_type": "entity.prop",
        }],
        "tracks": [],
    }


def _mapping() -> dict:
    return {"entities": {"Guard": {"actor_label": "TargetGuard"}}, "assets": {}}


def _curve(value: float, path: str = "", *, times=(0, 1)) -> dict:
    return {
        "path": path, "canonical_semantic": "transform.position.x",
        "property_name": "m_LocalPosition.x",
        "keys": [{"time_seconds": t, "value": value} for t in times],
    }


def _with_transform(curves, *, offset=0):
    source = _source()
    source["tracks"] = [{
        "ced_type": "animation.track", "binding_entity_id": "guard-id",
        "sections": [{
            "start": _time(0), "end": _time(1),
            "source_offset": _time(offset), "time_scale": 1.0,
            "payload": {"animation": {"curves": curves}},
        }],
    }]
    return source


def _transform_keys(source):
    plan = csir_plan.build_plan(source, _mapping())
    return [action["keys"] for action in plan["actions"]
            if action["kind"] == "transform"]


def test_duplicate_source_object_identifiers_fail_closed():
    source = _source()
    source["entities"].append({
        "entity_id": "guard-id", "name": "Camera", "ced_type": "entity.camera",
    })
    with pytest.raises(csir_plan.PlanError, match="duplicated source entity_id"):
        csir_plan.build_plan(source, _mapping())


def test_duplicate_mapped_source_names_cannot_share_one_target_identity():
    source = _source()
    source["entities"].append({
        "entity_id": "second", "name": "Guard", "ced_type": "entity.prop",
    })
    with pytest.raises(csir_plan.PlanError, match="Ambiguous mapped source entity"):
        csir_plan.build_plan(source, _mapping())


def test_two_mapped_source_entities_cannot_bind_same_unreal_actor():
    source = _source()
    source["entities"].append({
        "entity_id": "camera-id", "name": "Camera", "ced_type": "entity.camera",
    })
    mapping = _mapping()
    mapping["entities"]["Camera"] = {"actor_label": "TargetGuard"}
    with pytest.raises(csir_plan.PlanError, match="same Unreal actor"):
        csir_plan.build_plan(source, mapping)


def test_duplicate_source_asset_ids_and_mapped_asset_names_fail_closed():
    source = _source()
    source["assets"] = [{"asset_id": "clip", "name": "Walk"},
                        {"asset_id": "clip", "name": "Run"}]
    with pytest.raises(csir_plan.PlanError, match="duplicated source asset_id"):
        csir_plan.build_plan(source, _mapping())
    source["assets"][1]["asset_id"] = "clip2"
    source["assets"][1]["name"] = "Walk"
    mapping = _mapping()
    mapping["assets"]["Walk"] = "/Game/Walk.Walk"
    with pytest.raises(csir_plan.PlanError, match="Ambiguous mapped source asset"):
        csir_plan.build_plan(source, mapping)


def test_unmapped_repeated_names_do_not_break_safe_subset_transfer():
    source = _source()
    source["entities"].extend([
        {"entity_id": "prop-a", "name": "Unmapped Cube"},
        {"entity_id": "prop-b", "name": "Unmapped Cube"},
    ])
    assert csir_plan.build_plan(source, _mapping())["bindings"] == {"Guard": "TargetGuard"}


def test_duplicate_loaded_unreal_actor_labels_are_not_unique_matches():
    source = _source()
    proposal = asset_resolver.propose(
        source, target_actor_labels=["Guard", "Guard"], target_asset_paths=[],
    )
    assert proposal["actors"][0]["status"] == "AMBIGUOUS"
    assert proposal["actors"][0]["auto_applied"] is False


def test_nested_bone_position_cannot_override_owning_actor_translation():
    # The nested bone curve may follow the exact same canonical semantic
    # but lives at a distinct Unity AnimationCurve binding path.
    keys = _transform_keys(_with_transform([
        _curve(1.0, path=""),
        _curve(99.0, path="Armature/Hips/Spine"),
    ]))
    assert len(keys) == 1
    assert all(abs(k["location_cm"][1] - 100.0) < 1e-8 for k in keys[0])


def test_bone_only_curves_do_not_fabricate_unreal_actor_motion():
    assert _transform_keys(_with_transform([
        _curve(123.0, path="Armature/Hips"),
    ])) == []


def test_duplicate_root_curve_mapping_refuses_rather_than_last_writer_wins():
    with pytest.raises(csir_plan.PlanError, match="duplicate root-level"):
        _transform_keys(_with_transform([_curve(1.0), _curve(100.0)]))


@pytest.mark.parametrize("keys", [
    [{"time_seconds": 1.0, "value": 2}, {"time_seconds": 0.0, "value": 3}],
    [{"time_seconds": 0.0, "value": 1}, {"time_seconds": 0.0, "value": 5}],
    [{"time_seconds": 0.0, "value": float("inf")}],
])
def test_malformed_scalar_key_timing_or_value_never_reconstructs_silently(keys):
    with pytest.raises(csir_plan.PlanError, match="Source animation|Non-finite"):
        csir_plan._curve_value({"keys": keys}, 0.5)


def test_native_weighted_curve_is_rejected_even_at_start_boundary():
    curve = {"native_keys": [1], "keys": [
        {"time_seconds": 0.0, "value": 0.0, "weighted_mode": 2},
        {"time_seconds": 1.0, "value": 1.0, "weighted_mode": 0},
    ]}
    with pytest.raises(csir_plan.PlanError, match="Weighted Unity"):
        csir_plan._curve_value(curve, 0.0)


def test_trimmed_clip_holds_source_endpoint_even_with_no_key_in_window():
    source = _with_transform([_curve(3.0)], offset=2)
    keys = _transform_keys(source)
    assert len(keys) == 1
    assert [key["frame"] for key in keys[0]] == [0, 30]
    assert all(abs(key["location_cm"][1] - 300.0) < 1e-8 for key in keys[0])
