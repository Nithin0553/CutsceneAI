"""Nonidentity source group transforms must be incorporated exactly once.

This proves the deterministic planner's world-space transfer basis, not
native target playback. Editable group actors require a separate strategy.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "integrations" / "unreal"))

import csir_plan
import scene_prep


def test_benchmark002_nonidentity_root_world_pose_does_not_get_lost():
    # Values from the Unity source grouping object in Benchmark002 CSIR.
    root = (0.0170499999076128, 0.0, -5.902160167694092)
    local = (-3.5, 0.0, 0.0)
    world, rotation, scale = csir_plan.compose_canonical_transform(
        root, (0.0, 0.0, 0.0, 1.0), (1.0, 1.0, 1.0),
        local, (0.0, 0.0, 0.0, 1.0),
    )
    assert world == pytest.approx((-3.482949999, 0.0, -5.90216016769))
    assert rotation == pytest.approx((0.0, 0.0, 0.0, 1.0))
    assert scale == (1.0, 1.0, 1.0)
    ue = csir_plan.canonical_position_to_unreal_cm(world)
    assert ue == pytest.approx((590.216016769, -348.2949999, 0.0))


def test_source_world_scene_actor_initialization_is_world_not_local():
    entity = {
        "name": "PROP_MOVING",
        "metadata": {
            "world_transform": {
                "position": {"x": -3.482949972, "y": 0.0, "z": -5.9021601677},
                "rotation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
                "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
            },
        },
    }
    operation = scene_prep._world_transform(entity, "CSAI_PROP_MOVING")
    assert operation["source"] == "entity.world_transform"
    assert operation["location_cm"] == pytest.approx((590.21601677, -348.2949972, 0.0))


def test_rotated_scaled_group_must_use_full_quaternion_composition():
    # Mapping children by adding local coordinates without rotating and
    # scaling the parent would be wrong for general game cinematics.
    import math

    turn = math.sqrt(0.5)
    out, _, _ = csir_plan.compose_canonical_transform(
        (10.0, 0.0, 0.0), (0.0, turn, 0.0, turn), (2.0, 1.0, 1.0),
        (1.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0),
    )
    assert out == pytest.approx((10.0, 0.0, -2.0), abs=1e-8)
