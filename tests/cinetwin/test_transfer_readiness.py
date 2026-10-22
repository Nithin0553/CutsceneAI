"""Generic readiness gate regression tests: source information is never dropped silently."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "cinetwin"))
import transfer_readiness


def clock(seconds):
    return {
        "value": int(seconds * 1000000),
        "rate": {"numerator": 1000000, "denominator": 1},
    }


def section(asset=None, curves=None):
    return {
        "section_id": "clip:1",
        "start": clock(0),
        "end": clock(2),
        "source_offset": clock(0),
        "time_scale": 1.0,
        "payload": {
            "asset_id": asset,
            "animation": {"curves": curves or []},
        },
    }


def source(tracks):
    return {
        "schema_version": "0.1.0",
        "source": {"engine": "unity"},
        "timing": {
            "source_rate": {"numerator": 24, "denominator": 1},
            "duration_seconds": 2.0,
        },
        "assets": [{"asset_id": "asset:run", "name": "Jogging"}],
        "entities": [
            {"entity_id": "entity:robot", "name": "StudioRobot", "ced_type": "entity.character"},
            {"entity_id": "entity:crate", "name": "OrangeCrate", "ced_type": "entity.prop"},
        ],
        "tracks": tracks,
    }


def mapping():
    return {
        "entities": {
            "StudioRobot": {"actor_label": "RobotUE"},
            "OrangeCrate": {"actor_label": "CrateUE"},
        },
        "assets": {"Jogging": "/Game/Jog"},
        "sequence_asset_path": "/Game/Tests/TestCutscene",
    }


def skeletal():
    return {
        "track_id": "anim:robot", "name": "Any animation",
        "ced_type": "animation.track", "binding_entity_id": "entity:robot",
        "sections": [section("asset:run")],
    }


def prop_motion():
    return {
        "track_id": "prop:move", "name": "Any prop animation",
        "ced_type": "animation.track", "binding_entity_id": "entity:crate",
        "sections": [section(curves=[{
            "canonical_semantic": "transform.position.x",
            "keys": [{"time_seconds": 0.0, "value": 0.0},
                     {"time_seconds": 2.0, "value": 2.0}],
        }])],
    }


def test_arbitrary_named_scene_has_complete_explicit_ledger():
    tracks = [skeletal(), prop_motion(), {
        "track_id": "signal:1", "name": "Trigger",
        "ced_type": "event.trigger", "sections": [section()],
    }]
    report = transfer_readiness.audit(source(tracks), mapping())
    assert report["generation"] == "READY_FOR_ENGINE_PREFLIGHT"
    assert report["fidelity"] == "NOT_ESTABLISHED"
    assert report["source_track_count"] == 3
    assert report["unaccounted_track_count"] == 0
    assert [r["state"] for r in report["tracks"]] == [
        "PARTIAL", "COVERED", "PARTIAL"
    ]
    assert report["planned_actions"]["skeletal_animation"] == 1
    assert report["planned_actions"]["transform"] == 1
    assert report["planned_actions"]["marker"] == 1


def test_missing_imported_skeletal_asset_prevents_false_generation_success():
    target = mapping()
    target["assets"] = {}
    report = transfer_readiness.audit(source([skeletal()]), target)
    assert report["generation"] == "BLOCKED"
    assert report["tracks"][0]["state"] == "BLOCKED"
    assert "without mapped target assets" in report["tracks"][0]["reasons"][0]


def test_unknown_track_is_reported_not_skipped():
    unknown = {
        "track_id": "script:1", "name": "Cutscene script",
        "ced_type": "custom.script.event",
        "sections": [section()],
    }
    report = transfer_readiness.audit(source([unknown]), mapping())
    assert report["generation"] == "BLOCKED"
    assert report["counts"] == {"BLOCKED": 1}


def test_mute_and_empty_tracks_are_accounted_for():
    tracks = [
        {**skeletal(), "muted": True},
        {**prop_motion(), "sections": []},
    ]
    report = transfer_readiness.audit(source(tracks), mapping())
    assert report["generation"] == "READY_FOR_ENGINE_PREFLIGHT"
    assert report["source_track_count"] == 2
    assert report["counts"] == {"SKIPPED": 2}
    assert report["planned_actions"] == {}


def test_missing_actor_mapping_blocks_early():
    target = mapping()
    target["entities"].pop("StudioRobot")
    report = transfer_readiness.audit(source([skeletal()]), target)
    assert report["generation"] == "BLOCKED"
    assert "No mapped Unreal actor" in report["tracks"][0]["reasons"][0]


def test_motion_without_supported_curves_does_not_fake_motion():
    unknown = prop_motion()
    unknown["sections"][0]["payload"]["animation"]["curves"] = [{
        "canonical_semantic": "material.emissive",
        "keys": [{"time_seconds": 0, "value": 1}],
    }]
    report = transfer_readiness.audit(source([unknown]), mapping())
    assert report["generation"] == "BLOCKED"
    assert "No supported animated" in report["tracks"][0]["reasons"][0]
