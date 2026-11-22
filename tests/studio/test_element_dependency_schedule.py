"""Element 3.2 dependency ordering, ownership safety and independent regrounding."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for folder in ("studio", "ced"):
    sys.path.insert(0, str(ROOT / "packages" / folder))

import ced_agent_knowledge as ced
import studio_element_plan as plans
import studio_element_schedule as schedules


def _time(ticks: int) -> dict:
    return {"value": ticks, "rate": {"numerator": 1, "denominator": 1}}


def _clip(ident: str, *, start: int = 0, end: int = 10, blend: bool = False) -> dict:
    section = {
        "section_id": ident, "ced_type": "animation.clip",
        "start": _time(start), "end": _time(end),
        "payload": {"animation": {"curves": [
            {"canonical_semantic": "transform.position", "curve_id": ident + "-curve"}
        ]}},
    }
    if blend:
        section["native_payload"] = {"blend_in_seconds": 1}
    return section


def _scene() -> dict:
    return {
        "assets": [{"asset_id": "SECRET-ASSET", "ced_type": "asset.model"}],
        "entities": [
            {"entity_id": "ROOT-RAW-ID", "ced_type": "entity.prop"},
            {"entity_id": "CHARACTER-RAW-ID", "ced_type": "entity.character",
             "parent_entity_id": "ROOT-RAW-ID", "asset_id": "SECRET-ASSET"},
        ],
        "tracks": [
            {"track_id": "PRIVATE-TRACK-A", "ced_type": "animation.track",
             "binding_entity_id": "CHARACTER-RAW-ID",
             "sections": [_clip("PRIVATE-CLIP-A")]},
        ],
        "relationships": [],
    }


def _prepared(source: dict) -> tuple[dict, dict, dict]:
    capabilities = {
        "cine_camera_actor": True,
        "sequencer_skeletal_animation_track": True,
        "sequencer_visibility_track": True,
        "fbx_asset_import": True,
    }
    knowledge = ced.retrieve_all(source, target_capabilities=capabilities)
    plan = plans.prepare(source, knowledge, capabilities)
    return plan, knowledge, capabilities


def _by_location(plan: dict) -> dict:
    return {row["source_location"]: row["occurrence_id"] for row in plan["elements"]}


def _status(schedule: dict) -> dict:
    return {row["occurrence_id"]: row["status"] for row in schedule["nodes"]}


def test_source_dependencies_have_stable_topological_waves_and_complete_identity():
    source = _scene()
    plan, _, _ = _prepared(source)
    first = schedules.build(plan, source)
    second = schedules.build(plan, source)
    assert first == second
    assert first["native_execution_permitted"] is False
    assert first["fidelity_verified"] is False
    ids = _by_location(plan)
    layer = {ident: i for i, wave in enumerate(first["topological_waves"])
             for ident in wave}
    assert layer[ids["assets[0]"]] < layer[ids["entities[1]"]]
    assert layer[ids["entities[0]"]] < layer[ids["entities[1]"]]
    assert layer[ids["entities[1]"]] < layer[ids["tracks[0]"]]
    assert layer[ids["tracks[0]"]] < layer[ids["tracks[0].sections[0]"]]
    assert (layer[ids["tracks[0].sections[0]"]]
            < layer[ids["tracks[0].sections[0].payload.animation.curves[0]"]])
    assert len(layer) == plan["source_occurrence_count"]
    assert first["unscheduled_occurrences"] == []
    assert first["advisory_candidate_waves"] == []
    assert "PRIVATE" not in json.dumps(first)
    assert "SECRET" not in json.dumps(first)
    schedules.verify(first, plan, source)


def test_cyclic_parentage_flags_cycle_and_separate_downstream_blocker():
    source = {
        "entities": [
            {"entity_id": "A", "ced_type": "entity.prop", "parent_entity_id": "B"},
            {"entity_id": "B", "ced_type": "entity.prop", "parent_entity_id": "A"},
            {"entity_id": "C", "ced_type": "entity.prop", "parent_entity_id": "A"},
        ]
    }
    plan, _, _ = _prepared(source)
    schedule = schedules.build(plan, source)
    ids = _by_location(plan)
    states = _status(schedule)
    assert states[ids["entities[0]"]] == "DEPENDENCY_CYCLE"
    assert states[ids["entities[1]"]] == "DEPENDENCY_CYCLE"
    assert states[ids["entities[2]"]] == "UPSTREAM_BLOCKED"
    assert set(schedule["unscheduled_occurrences"]) == set(ids.values())
    schedules.verify(schedule, plan, source)


def test_missing_parent_dependency_propagates_without_inventing_action():
    source = _scene()
    source["entities"][1]["parent_entity_id"] = "UNRESOLVED"
    plan, _, _ = _prepared(source)
    schedule = schedules.build(plan, source)
    states = _status(schedule)
    ids = _by_location(plan)
    assert states[ids["entities[1]"]] == "SOURCE_DEPENDENCY_MISSING"
    assert states[ids["tracks[0]"]] == "UPSTREAM_BLOCKED"
    assert states[ids["tracks[0].sections[0]"]] == "UPSTREAM_BLOCKED"


def test_overlap_and_multiple_transform_track_writers_cannot_be_assumed_safe():
    source = _scene()
    source["tracks"].append({
        "track_id": "PRIVATE-TRACK-B", "ced_type": "animation.track",
        "binding_entity_id": "CHARACTER-RAW-ID",
        "sections": [_clip("PRIVATE-CLIP-B", start=5, end=12)],
    })
    plan, _, _ = _prepared(source)
    schedule = schedules.build(plan, source)
    kinds = {row["kind"] for row in schedule["conflicts"]}
    assert "MULTIPLE_TRANSFORM_TRACK_WRITERS" in kinds
    assert "OVERLAPPING_SECTION_WRITERS" in kinds
    ids = _by_location(plan)
    states = _status(schedule)
    assert states[ids["tracks[0]"]] == "OWNERSHIP_CONFLICT"
    assert states[ids["tracks[1]"]] == "OWNERSHIP_CONFLICT"
    assert states[ids["tracks[0].sections[0]"]] == "OWNERSHIP_CONFLICT"
    assert "CHARACTER-RAW-ID" not in json.dumps(schedule)
    schedules.verify(schedule, plan, source)


def test_independent_bindings_do_not_conflict_and_native_easing_is_explicit():
    source = _scene()
    source["entities"].append({"entity_id": "INDEPENDENT-CHAR", "ced_type": "entity.character"})
    source["tracks"].append({
        "track_id": "OTHER-TRACK", "ced_type": "animation.track",
        "binding_entity_id": "INDEPENDENT-CHAR",
        "sections": [_clip("OTHER-CLIP", start=0, end=8)],
    })
    plan, _, _ = _prepared(source)
    assert schedules.build(plan, source)["conflicts"] == []
    source["tracks"][0]["sections"][0]["native_payload"] = {"ease_in_seconds": 1}
    plan, _, _ = _prepared(source)
    schedule = schedules.build(plan, source)
    assert {c["kind"] for c in schedule["conflicts"]} == {"UNBAKED_TIMELINE_BLEND"}


def test_missing_or_invalid_clip_timing_does_not_silently_prove_safe_writes():
    source = _scene()
    del source["tracks"][0]["sections"][0]["start"]
    plan, _, _ = _prepared(source)
    schedule = schedules.build(plan, source)
    assert "UNPROVEN_TIMING_OR_BLEND" in {c["kind"] for c in schedule["conflicts"]}
    ids = _by_location(plan)
    assert _status(schedule)[ids["tracks[0]"]] == "OWNERSHIP_CONFLICT"


def test_selected_actions_remain_advisory_and_depend_on_upstream_choices():
    source = {"entities": [{"entity_id": "CAMERA-ID", "ced_type": "entity.camera"}],
              "tracks": [{"track_id": "T", "ced_type": "camera.transform",
                          "binding_entity_id": "CAMERA-ID", "sections": []}]}
    plan, _, _ = _prepared(source)
    ids = _by_location(plan)
    # A selected camera track does not justify dispatch without its source
    # binding's planned preparation.
    candidates = next(row["candidate_actions"] for row in plan["elements"]
                      if row["source_location"] == "tracks[0]")
    if not candidates:
        pytest.skip("No registered transform action in this CED snapshot")
    choices = [{"occurrence_id": row["occurrence_id"],
                "action": candidates[0] if row["source_location"] == "tracks[0]"
                else "report_only"} for row in plan["elements"]]
    reviewed = plans.apply_choices(plan, choices, expected_ids=list(ids.values()))
    schedule = schedules.build(reviewed, source)
    assert _status(schedule)[ids["tracks[0]"]] == "UPSTREAM_NOT_PLANNED"
    assert schedule["advisory_candidate_waves"] == []
    # Even independently selected, source-grounded actor preparation is only
    # an unexecuted proposal and must go through separate native preflight.
    camera_action = next(row["candidate_actions"][0] for row in plan["elements"]
                         if row["source_location"] == "entities[0]")
    choices[0]["action"] = camera_action
    reviewed = plans.apply_choices(plan, choices, expected_ids=list(ids.values()))
    schedule = schedules.build(reviewed, source)
    assert _status(schedule)[ids["tracks[0]"]] == "ADVISORY_PREFLIGHT_REQUIRED"
    assert schedule["native_execution_permitted"] is False


def test_recomputed_checksum_cannot_launder_changed_order_or_hidden_conflict():
    source = _scene()
    plan, _, _ = _prepared(source)
    schedule = schedules.build(plan, source)
    falsified = copy.deepcopy(schedule)
    falsified["topological_waves"] = list(reversed(falsified["topological_waves"]))
    falsified.pop("schedule_sha256")
    falsified["schedule_sha256"] = plans._digest(falsified)
    with pytest.raises(schedules.ElementScheduleError, match="tampered"):
        schedules.verify(falsified, plan, source)


def test_large_scene_is_fully_ordered_without_truncation():
    source = {"entities": [
        {"entity_id": f"cam-{i}", "ced_type": "entity.camera"}
        for i in range(300)
    ]}
    plan, _, _ = _prepared(source)
    schedule = schedules.build(plan, source)
    assert plan["source_occurrence_count"] == 300
    assert len(schedule["nodes"]) == 300
    assert len(schedule["topological_waves"][0]) == 300
    assert schedule["unscheduled_occurrences"] == []
    schedules.verify(schedule, plan, source)


def test_muted_track_and_unbound_writer_are_not_executable_assumptions():
    source = _scene()
    source["tracks"][0]["muted"] = True
    plan, _, _ = _prepared(source)
    schedule = schedules.build(plan, source)
    assert "MUTED_SOURCE_TRACK" in {c["kind"] for c in schedule["conflicts"]}
    assert _status(schedule)[_by_location(plan)["tracks[0]"]] == "OWNERSHIP_CONFLICT"

    source["tracks"][0]["muted"] = False
    source["tracks"][0].pop("binding_entity_id")
    plan, _, _ = _prepared(source)
    schedule = schedules.build(plan, source)
    assert "UNPROVEN_TRACK_BINDING" in {c["kind"] for c in schedule["conflicts"]}


def test_global_camera_cuts_have_shared_sequence_ownership():
    source = {"tracks": [
        {"track_id": "GLOBAL-CUT-A", "ced_type": "camera.cut",
         "sections": [{
             "section_id": "FIRST-CUT", "ced_type": "camera.cut",
             "start": _time(0), "end": _time(10), "payload": {},
         }]},
        {"track_id": "GLOBAL-CUT-B", "ced_type": "camera.cut",
         "sections": [{
             "section_id": "SECOND-CUT", "ced_type": "camera.cut",
             "start": _time(6), "end": _time(12), "payload": {},
         }]},
    ]}
    plan, _, _ = _prepared(source)
    schedule = schedules.build(plan, source)
    assert "OVERLAPPING_SECTION_WRITERS" in {c["kind"] for c in schedule["conflicts"]}
    ids = _by_location(plan)
    states = _status(schedule)
    assert states[ids["tracks[0]"]] == "OWNERSHIP_CONFLICT"
    assert states[ids["tracks[1]"]] == "OWNERSHIP_CONFLICT"
    schedules.verify(schedule, plan, source)
