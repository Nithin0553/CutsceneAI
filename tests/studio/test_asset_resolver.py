"""Only unambiguous exact actor/asset matches are suggested to the operator."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "studio"))

import asset_resolver


def source():
    return {
        "cutscene_id": "cutscene:unseen",
        "entities": [
            {"entity_id": "A", "name": "CHARACTER_A", "ced_type": "entity.character"},
            {"entity_id": "B", "name": "CAM_B_Wide", "ced_type": "entity.camera"},
        ],
        "assets": [
            {"asset_id": "a1", "name": "Walk Cycle"},
            {"asset_id": "a2", "name": "Ambience"},
        ],
    }


def test_exact_unique_mappings_are_never_applied_automatically():
    report = asset_resolver.propose(
        source(),
        target_actor_labels=["CHARACTER_A", "cam b wide", "Other"],
        target_asset_paths=["/Game/Animations/Walk_Cycle.Walk_Cycle",
                            "/Game/Sounds/Ambience.Ambience"],
    )
    assert all(x["status"] == "EXACT_UNIQUE_PROPOSAL" for x in report["actors"])
    assert all(x["status"] == "EXACT_UNIQUE_PROPOSAL" for x in report["assets"])
    assert report["assets"][0]["candidates"] == [
        "/Game/Animations/Walk_Cycle.Walk_Cycle"
    ]
    assert report["automatically_applied"] is False
    assert all(x["auto_applied"] is False for x in report["assets"])


def test_ambiguity_must_block_guessing():
    report = asset_resolver.propose(
        source(),
        target_actor_labels=["CHARACTER_A", "CHARACTER-A"],
        target_asset_paths=["/Game/A/Walk_Cycle", "/Game/B/WalkCycle"],
    )
    assert report["actors"][0]["status"] == "AMBIGUOUS"
    assert len(report["actors"][0]["candidates"]) == 2
    assert report["assets"][0]["status"] == "AMBIGUOUS"


def test_missing_asset_import_is_needs_mapping_not_faked():
    report = asset_resolver.propose(
        source(), target_actor_labels=[], target_asset_paths=[]
    )
    assert report["actors"][0]["status"] == "NEEDS_MAPPING_OR_IMPORT"
    assert report["assets"][0]["status"] == "NEEDS_MAPPING_OR_IMPORT"
    assert report["assets"][0]["candidates"] == []
