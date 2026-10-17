"""Contract tests for non-destructive Unreal CineTwin runtime observations."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "cinetwin"))

import target_observation_plan as observer


def _sampling_plan() -> dict:
    return {
        "kind": "cinetwin.sampling_plan",
        "cutscene_id": "example",
        "source": {
            "engine": "unity", "csir_sha256": "a" * 64
        },
        "samples": [
            {"time_seconds": 0.0},
            {"time_seconds": 1.0},
            {"time_seconds": 2.0},
        ],
        "entities": [
            {
                "entity_id": "actor1", "name": "Actor",
                "ced_type": "entity.character",
            },
            {
                "entity_id": "cam1", "name": "Camera",
                "ced_type": "entity.camera",
            },
            {
                "entity_id": "unmapped", "name": "Audio",
                "ced_type": "entity.audio",
            },
        ],
        "skeletal_entity_ids": ["actor1"],
    }


def _mapping() -> dict:
    return {
        "entities": {
            "Actor": {"actor_label": "CHARACTER_A"},
            "Camera": {"actor_label": "CAM_A"},
        }
    }


def test_observer_resolves_mapped_actors_and_reports_unmapped() -> None:
    resolved = observer.prepare_observation(_sampling_plan(), _mapping())
    assert resolved["selected_times_seconds"] == [0.0, 1.0, 2.0]
    assert len(resolved["bound"]) == 2
    assert len(resolved["missing"]) == 1
    assert resolved["missing"][0]["source_name"] == "Audio"
    assert len(resolved["skeletal_rigs"]) == 1
    assert resolved["skeletal_rigs"][0]["entity_id"] == "actor1"


def test_smoke_test_uses_at_most_selected_sample_count() -> None:
    resolved = observer.prepare_observation(
        _sampling_plan(), _mapping(), max_samples=2
    )
    assert resolved["selected_times_seconds"] == [0.0, 1.0]
    assert resolved["full_sample_count"] == 3


def test_missing_skeletal_mapping_is_a_hard_blocker() -> None:
    mapping = _mapping()
    del mapping["entities"]["Actor"]
    with pytest.raises(observer.TargetPlanError, match="animated source rigs"):
        observer.prepare_observation(_sampling_plan(), mapping)


def test_collision_in_actor_mappings_is_a_hard_blocker() -> None:
    mapping = _mapping()
    mapping["entities"]["Camera"]["actor_label"] = "CHARACTER_A"
    with pytest.raises(observer.TargetPlanError, match="same actor label"):
        observer.prepare_observation(_sampling_plan(), mapping)


@pytest.mark.parametrize(
    "sample_times",
    [
        [],
        [0.0, 0.0],
        [2.0, 1.0],
        [0.0, float("nan")],
    ],
)
def test_invalid_sample_times_block_capture(sample_times) -> None:
    plan = _sampling_plan()
    plan["samples"] = [{"time_seconds": t} for t in sample_times]
    with pytest.raises(observer.TargetPlanError):
        observer.prepare_observation(plan, _mapping())


def test_invalid_smoke_test_size_blocks_capture() -> None:
    with pytest.raises(observer.TargetPlanError):
        observer.prepare_observation(
            _sampling_plan(), _mapping(), max_samples=0
        )


def test_unreal_observer_contract_guards_actual_evaluation_and_no_writes() -> None:
    source = (
        ROOT / "integrations/unreal/cinetwin_target_evaluator.py"
    ).read_text(encoding="utf-8")
    ast.parse(source)
    assert "MovieSceneSequencePlaybackParams" in source
    assert "MovieScenePositionType.TIME" in source
    assert "UpdatePositionMethod.JUMP" in source
    assert "set_global_position" in source
    assert "force_update" in source
    assert "get_actor_location()" in source
    assert "get_bone_transform" in source
    assert "unreal_position_cm_to_canonical_m" in source
    assert "unmapped_source_entities" in source
    assert "NOT_IMPLEMENTED_REQUIRES_BONE_MAPPING" in source
    assert "save_loaded_asset" not in source
    assert "set_actor_location(" not in source
    assert "set_actor_rotation(" not in source
