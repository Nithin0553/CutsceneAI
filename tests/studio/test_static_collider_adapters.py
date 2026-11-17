"""Exercise Unity census -> Studio plan -> native shape staging -> readback."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
for relative in ("integrations/unreal", "packages/cinetwin", "packages/studio"):
    sys.path.insert(0, str(ROOT / relative))

import studio_collider_shapes
import transfer_backend
from test_adaptive_components import _native_light_inputs

VARIANTS = {
    "box": ("BoxCollider", "LOSSY_SCALE_NO_SHEAR_PROOF",
            {"world_size_m": {"x": 2.0, "y": 4.0, "z": 6.0}}),
    "sphere": ("SphereCollider", "UNITY_SPHERE_MAX_AXIS_LOSSY_SCALE", {"world_radius_m": 0.4}),
    "capsule": ("CapsuleCollider", "UNITY_CAPSULE_UNIFORM_SCALE",
                {"world_radius_m": 0.4, "world_height_m": 2.2}),
}


def _inputs(tmp_path, shapes):
    paths, (csir, mapping, census) = _native_light_inputs(tmp_path)
    mapping["enable_native_component_staging"] = True
    entity = {
        "entity_id": "prop-static", "name": "Wall", "ced_type": "entity.prop",
        "native_ref": "wall-global-id",
        "metadata": {"scene_path": "Assets/Stages/Interior.unity", "hierarchy_path": "Set/Wall"},
    }
    csir["entities"].append(entity)
    mapping["entities"]["Wall"] = {"actor_label": "WallUE"}
    identity = {
        "scene_path": "Assets/Stages/Interior.unity", "object_path": "Set/Wall",
        "global_object_id": "wall-global-id",
    }
    rows = census["loaded_scene_components"]
    rows.append({**identity, "component_type": "UnityEngine.Transform",
                 "component_global_id": "wall-transform"})
    for shape in shapes:
        component, policy, fields = VARIANTS[shape]
        rows.append({
            **identity, "component_type": "UnityEngine." + component,
            "component_assembly": "UnityEngine.PhysicsModule",
            "component_global_id": "wall-" + shape,
            "feature": {
                "extraction": "STATIC_COLLIDER_WORLD_SHAPE_CANDIDATE",
                "shape": shape, "has_geometry": True, "enabled": True, "is_trigger": False,
                "world_center_m": {"x": -1.0, "y": 2.0, "z": 3.0},
                "world_rotation_xyzw": {"x": 0, "y": 0, "z": math.sqrt(0.5), "w": math.sqrt(0.5)},
                "collider_scale_policy": policy, "native_properties_truncated": False,
                "primitive_snapshot_version": "1.0.0", "primitive_transform_supported": True,
                "collider_owner_static": True, "collider_has_body": False,
                "collider_owner_active": True, **fields,
            },
        })
    return paths, (csir, mapping, census)


def _plan(paths, inputs):
    for path, value in zip(paths, inputs):
        path.write_text(json.dumps(value), encoding="utf-8")
    return transfer_backend.compose_files(*paths[:2])


def test_native_collider_planner_converts_basis_units_and_retains_identity(tmp_path):
    plan, report, _ = _plan(*_inputs(tmp_path, VARIANTS))
    actions = {action["shape"]: action for action in studio_collider_shapes.from_plan(plan)}
    assert len(actions) == 3
    assert len({action["collider_label"] for action in actions.values()}) == 3
    assert all(action["location_cm"] == [300.0, -100.0, 200.0] for action in actions.values())
    assert actions["box"]["box_extent_cm"] == [300.0, 100.0, 200.0]
    assert actions["sphere"]["radius_cm"] == 40.0
    assert actions["capsule"]["half_height_cm"] == pytest.approx(110)
    assert all(action["source_object_id"] == "wall-global-id" for action in actions.values())
    records = report["component_transfer_ledger"]["records"]
    planned = [row for row in records if row["target_action_planned"]]
    assert {row["source_component_id"] for row in planned} == {
        "wall-box", "wall-sphere", "wall-capsule", "light-component-id",
    }
    assert not any(row["behavior_verified"] or row["release_eligible"] for row in planned)


@pytest.mark.parametrize(("invalid", "status"), [
    ("legacy", "REQUIRED_SOURCE_COMPONENT_FIELDS_MISSING"),
    ("shear", "COLLIDER_TRANSFORM_OR_SNAPSHOT_UNSUPPORTED"),
    ("dynamic", "DYNAMIC_COLLIDER_NEEDS_SIMULATION_ADAPTER"),
    ("animated", "TIMELINE_BOUND_COLLIDER_NEEDS_MOTION_ADAPTER"),
    ("nonunit", "SOURCE_COLLIDER_ROTATION_NOT_UNIT"),
    ("no-stage", "AUTOMATIC_SCENE_STAGING_REQUIRED"),
])
def test_unsupported_source_leaves_unrelated_adapters_operational(tmp_path, invalid, status):
    paths, (csir, mapping, census) = _inputs(tmp_path, ["box"])
    feature = census["loaded_scene_components"][-1]["feature"]
    if invalid == "legacy":
        del feature["primitive_snapshot_version"]
    elif invalid == "shear":
        feature["primitive_transform_supported"] = False
    elif invalid == "dynamic":
        feature["collider_has_body"] = True
    elif invalid == "animated":
        csir["entities"][-1]["parent_entity_id"] = "moving"
    elif invalid == "nonunit":
        feature["world_rotation_xyzw"]["w"] = 3.0
    elif invalid == "no-stage":
        del mapping["enable_native_component_staging"]
    plan, report, _ = _plan(paths, (csir, mapping, census))
    assert studio_collider_shapes.from_plan(plan) == []
    assert any(action.get("adapter_name") == "unity_light_shadow" for action in plan["actions"])
    decision = report["adaptive_components"]["decisions"][-1]
    assert decision["status"] == status
    assert decision["source_component_id"] == "wall-box"


def _vec(x, y, z):
    return SimpleNamespace(x=x, y=y, z=z)


class Shape:
    def __init__(self):
        self.generate_overlap_events = True
        self.profile = "OverlapAll"
        self.mode = "query"

    def set_editor_property(self, name, value):
        setattr(self, name, value)

    def get_editor_property(self, name):
        return getattr(self, name)

    def set_collision_profile_name(self, profile, _update):
        self.profile = profile

    def get_collision_profile_name(self):
        return self.profile

    def set_collision_enabled(self, mode):
        self.mode = mode

    def get_collision_enabled(self):
        return self.mode


class BoxComponent(Shape):
    def set_box_extent(self, extent, _update):
        self.extent = extent

    def get_unscaled_box_extent(self):
        return self.extent


class SphereComponent(Shape):
    def set_sphere_radius(self, radius, _update):
        self.radius = radius

    def get_unscaled_sphere_radius(self):
        return self.radius


class CapsuleComponent(SphereComponent):
    def set_capsule_size(self, radius, half_height, _update):
        self.radius, self.half_height = radius, half_height

    def get_unscaled_capsule_half_height(self):
        return self.half_height

    def get_unscaled_capsule_radius(self):
        return self.radius


class ColliderActor:
    def __init__(self, location, rotation):
        self.label = "Unnamed"
        self.location = location
        self.rotation = rotation
        self.collision = True
        self.root_component = self.shape_class()

    def get_class(self):
        return SimpleNamespace(get_name=lambda: type(self).__name__)

    def set_actor_label(self, label, *, mark_dirty):
        assert mark_dirty
        self.label = label

    def get_actor_label(self):
        return self.label

    def set_actor_enable_collision(self, enabled):
        self.collision = enabled

    def get_actor_enable_collision(self):
        return self.collision

    def get_components_by_class(self, cls):
        return [self.root_component] if isinstance(self.root_component, cls) else []

    def get_editor_property(self, name):
        return getattr(self, name)

    def get_actor_location(self):
        return self.location

    def get_actor_rotation(self):
        return self.rotation

    def get_actor_scale3d(self):
        return _vec(1, 1, 1)

    def get_attach_parent_actor(self):
        return None


class TriggerBox(ColliderActor):
    shape_class = BoxComponent


class TriggerSphere(ColliderActor):
    shape_class = SphereComponent


class TriggerCapsule(ColliderActor):
    shape_class = CapsuleComponent


class Editor:
    def __init__(self):
        self.actors = []

    def get_all_level_actors(self):
        return list(self.actors)

    def spawn_actor_from_class(self, cls, location, rotation):
        actor = cls(location, rotation)
        self.actors.append(actor)
        return actor

    def destroy_actor(self, actor):
        self.actors.remove(actor)
        return True


@pytest.fixture
def api():
    return SimpleNamespace(
        Vector=_vec, Rotator=SimpleNamespace, EditorActorSubsystem=Editor,
        CollisionEnabled=SimpleNamespace(NO_COLLISION="disabled"),
        TriggerBox=TriggerBox, TriggerSphere=TriggerSphere, TriggerCapsule=TriggerCapsule,
        BoxComponent=BoxComponent, SphereComponent=SphereComponent, CapsuleComponent=CapsuleComponent,
    )


def test_staged_native_shapes_are_read_back_and_tampered_dimensions_fail(tmp_path, api):
    plan, _, _ = _plan(*_inputs(tmp_path, VARIANTS))
    actions = studio_collider_shapes.from_plan(plan)
    editor, operations = Editor(), []
    studio_collider_shapes.stage(api, editor, actions, operations)
    assert len(operations) == 3
    assert all(op["status"] == "CREATED_IN_MEMORY_GEOMETRY_READ_BACK" for op in operations)
    changed = next(actor for actor in editor.actors if isinstance(actor, TriggerCapsule))
    changed.root_component.half_height += 20
    result = studio_collider_shapes.inspect(api, actions, editor.get_all_level_actors())
    assert [row["status"] for row in result] == ["PASS", "PASS", "FAIL"]
    assert result[-1]["geometry_comparison"]["length_errors_m"]["height"] == pytest.approx(0.4)
    assert all(row["collision_disabled"] and not row["behavior_verified"] for row in result)


def test_failed_native_stage_rolls_back_only_created_shapes(tmp_path, api, monkeypatch):
    plan, _, _ = _plan(*_inputs(tmp_path, ["box", "sphere"]))
    actions = studio_collider_shapes.from_plan(plan)
    editor, operations = Editor(), []
    existing = TriggerBox(_vec(0, 0, 0), SimpleNamespace(roll=0, pitch=0, yaw=0))
    editor.actors.append(existing)

    def fail_size(*_):
        raise RuntimeError("Native shape rejected")

    monkeypatch.setattr(SphereComponent, "set_sphere_radius", fail_size)
    with pytest.raises(RuntimeError, match="Native shape rejected"):
        studio_collider_shapes.stage(api, editor, actions, operations)
    assert editor.actors == [existing]
    assert [op["status"] for op in operations] == ["ROLLED_BACK", "ROLLED_BACK"]


def test_preflight_rejects_occupied_label_without_scene_writes(tmp_path, api):
    plan, _, _ = _plan(*_inputs(tmp_path, ["box"]))
    actions = studio_collider_shapes.from_plan(plan)
    editor = Editor()
    existing = TriggerBox(_vec(0, 0, 0), SimpleNamespace(roll=0, pitch=0, yaw=0))
    existing.label = actions[0]["collider_label"].lower()
    editor.actors.append(existing)
    with pytest.raises(studio_collider_shapes.ColliderStagingError, match="occupied"):
        studio_collider_shapes.stage(api, editor, actions, [])
    assert editor.actors == [existing]
