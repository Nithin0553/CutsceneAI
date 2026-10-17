"""Regression tests for editor-tick CineTwin observer protocol and quality gates."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "cinetwin"))
from tick_probe_quality import TickObservationError, choose_times, max_bone_motion_m


def _plan() -> dict:
    return {
        "samples": [
            {"time_seconds": 0.0},
            {"time_seconds": 0.5},
            {"time_seconds": 0.75},
            {"time_seconds": 1.0},
            {"time_seconds": 1.5},
            {"time_seconds": 2.25},
            {"time_seconds": 3.0},
        ]
    }


def _frame(x: float, *, name: str = "pelvis") -> dict:
    return {
        "skeletal_poses": [{
            "entity_id": "character",
            "bones": [
                {"bone_name": name, "world_position_m": [x, 0.0, 0.0]},
                {"bone_name": "head", "world_position_m": [x, 1.75, 0.0]},
            ],
        }]
    }


def test_time_selection_is_nearest_actual_source_instant() -> None:
    assert choose_times(_plan(), (0.0, 0.75, 1.5, 2.25, 3.0)) == [
        0.0, 0.75, 1.5, 2.25, 3.0
    ]
    assert choose_times(_plan(), None) == [
        0.0, 0.5, 0.75, 1.0, 1.5, 2.25, 3.0
    ]
    assert choose_times(_plan(), (0.0, 0.001, 0.75)) == [0.0, 0.75]


def test_unsorted_probe_times_and_out_of_range_rejected() -> None:
    for probe in ((3.0, 0.0), (), (0.0, 3.2), (float("nan"),)):
        with pytest.raises(TickObservationError):
            choose_times(_plan(), probe)


def test_nonfinite_or_nonincreasing_source_schedule_rejected() -> None:
    for times in ([0, 1, 1], [0, float("inf")], []):
        plan = {"samples": [{"time_seconds": t} for t in times]}
        with pytest.raises(TickObservationError):
            choose_times(plan, None)


def test_motion_quality_reports_metric_world_bone_displacement() -> None:
    samples = [_frame(0.0), _frame(0.1), _frame(1.3)]
    assert max_bone_motion_m(samples, "character") == pytest.approx(1.3)
    assert max_bone_motion_m([_frame(0.0), _frame(0.0)], "character") == 0


def test_missing_rig_or_changing_bone_names_is_not_accepted() -> None:
    with pytest.raises(TickObservationError, match="missing skeletal rig"):
        max_bone_motion_m([_frame(0.0), {"skeletal_poses": []}], "character")
    with pytest.raises(TickObservationError, match="changed bone topology"):
        max_bone_motion_m([_frame(0.0), _frame(0.5, name="pelvis_new")], "character")


def test_nonfinite_bone_state_fails_closed() -> None:
    with pytest.raises(TickObservationError, match="invalid bone"):
        max_bone_motion_m(
            [_frame(0.0), _frame(float("nan"))], "character"
        )


def test_tick_protocol_is_async_editor_only_and_restores_playhead() -> None:
    source = (
        ROOT / "integrations" / "unreal" / "cinetwin_tick_evaluator.py"
    ).read_text(encoding="utf-8")
    ast.parse(source)
    for token in (
        "register_slate_post_tick_callback",
        "unregister_slate_post_tick_callback",
        "ticks_per_sample",
        "self.wait_ticks",
        "set_global_position",
        "self.previous_position",
        "self.previous_sequence",
        "NO_BONE_MOTION_OBSERVED",
        "slate_post_tick_between_sequencer_seeks",
        "quality",
    ):
        assert token in source
    for forbidden in (
        "save_loaded_asset(",
        "set_actor_location(",
        "set_actor_rotation(",
        "set_update_animation_in_editor(",
        "set_editor_property(",
        "override_animation_data(",
    ):
        assert forbidden not in source
